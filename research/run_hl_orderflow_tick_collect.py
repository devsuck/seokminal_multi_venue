"""Hyperliquid 오더플로우 체결 틱 수집기 — tmux로 상시 실행.

대형체결/흡수 임계값 백테스트용 원시 데이터 축적이 목적. TradeEvent만 기록하고
OrderBookSnapshot은 버린다(가격 히스토리는 기존 REST 캔들로 별도 조달 가능하므로
북 스냅샷까지 저장할 필요 없음). 코인별로 독립된 재연결 루프를 돌려 한쪽 스트림이
끊겨도 다른 코인 수집에 영향 없다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path

from orderflow.hl_adapter import HyperliquidOrderflowClient
from orderflow.models import TradeEvent

_DATA_DIR = Path("research/data/hl_orderflow_tick")

COINS = ["BTC", "ETH"]
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0


def append_trades(coin: str, trades: list[dict]) -> None:
    if not trades:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{coin}_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for t in trades:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


async def run_coin_forever(
    coin: str,
    *,
    client: HyperliquidOrderflowClient | None = None,
    append_fn=append_trades,
    max_cycles: int | None = None,
) -> None:
    client = client or HyperliquidOrderflowClient()
    cycle = 0
    delay = RECONNECT_BASE_DELAY
    while max_cycles is None or cycle < max_cycles:
        received_trade = False
        try:
            async for event in client.stream(coin):
                if isinstance(event, TradeEvent):
                    received_trade = True
                    append_fn(coin, [event.model_dump()])
            if received_trade:
                # 정상적으로 체결을 수신하다 스트림이 종료된 경우 — 백오프 불필요
                delay = RECONNECT_BASE_DELAY
            else:
                # 구독 직후 체결 하나 없이 스트림이 끊긴 경우 — 반복되면 핫루프가 되므로
                # 예외 케이스와 동일하게 백오프 적용
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
        except Exception:
            logging.exception("HL orderflow stream failed for %s, reconnecting", coin)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        cycle += 1


async def run_forever(
    *,
    coins: list[str] = COINS,
    client_factory=lambda coin: HyperliquidOrderflowClient(),
    append_fn=append_trades,
    max_cycles: int | None = None,
) -> None:
    await asyncio.gather(
        *(
            run_coin_forever(coin, client=client_factory(coin), append_fn=append_fn, max_cycles=max_cycles)
            for coin in coins
        )
    )


if __name__ == "__main__":
    asyncio.run(run_forever())
