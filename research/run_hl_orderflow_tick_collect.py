"""Hyperliquid 오더플로우 체결 틱 + 뎁스(DOM) 수집기 — tmux로 상시 실행.

대형체결/흡수 임계값 백테스트용 원시 체결 데이터, DOM(wall_proximity/iceberg_refill)
백테스트용 heatmap_delta를 함께 축적. OrderBookSnapshot은 IB 수집기(run_ib_orderflow_tick_collect.py)와
동일하게 OrderflowAggregator를 통과시켜 heatmap_delta로 변환 후 저장 — 라이브 대시보드
렌더링과 동일 소스코드라 백테스트 로직이 슬쩍 달라지는 버그를 원천 차단한다(원시 북
스냅샷 자체는 안 남김, orderflow/manager.py와 동일 판단).
tick_size는 라이브(orderflow/manager.py TICK_SIZE_BY_SYMBOL)와 동일 값을 그대로 참조해
연구용 신호와 라이브 렌더링 버킷팅이 어긋나지 않게 한다. 코인별로 독립된 재연결 루프를
돌려 한쪽 스트림이 끊겨도 다른 코인 수집에 영향 없다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path

from orderflow.aggregator import OrderflowAggregator
from orderflow.hl_adapter import HyperliquidOrderflowClient
from orderflow.manager import DEFAULT_TICK_SIZE, TICK_SIZE_BY_SYMBOL
from orderflow.models import OrderBookSnapshot, TradeEvent

_DATA_DIR = Path("research/data/hl_orderflow_tick")
_DEPTH_DATA_DIR = Path("research/data/hl_orderflow_depth")

COINS = ["BTC", "ETH", "PAXG"]
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


def append_depth(coin: str, deltas: list[dict]) -> None:
    if not deltas:
        return
    _DEPTH_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DEPTH_DATA_DIR / f"{coin}_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for d in deltas:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


async def run_coin_forever(
    coin: str,
    *,
    client: HyperliquidOrderflowClient | None = None,
    append_fn=append_trades,
    depth_append_fn=append_depth,
    aggregator: OrderflowAggregator | None = None,
    max_cycles: int | None = None,
) -> None:
    client = client or HyperliquidOrderflowClient()
    symbol = f"{coin}.HL"
    aggregator = aggregator or OrderflowAggregator(tick_size=TICK_SIZE_BY_SYMBOL.get(symbol, DEFAULT_TICK_SIZE))
    cycle = 0
    delay = RECONNECT_BASE_DELAY
    while max_cycles is None or cycle < max_cycles:
        received_trade = False
        try:
            async for event in client.stream(coin):
                if isinstance(event, TradeEvent):
                    received_trade = True
                    append_fn(coin, [event.model_dump()])
                elif isinstance(event, OrderBookSnapshot):
                    received_trade = True
                    deltas = aggregator.on_book_snapshot(event)
                    if deltas:
                        depth_append_fn(coin, deltas)
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
    depth_append_fn=append_depth,
    max_cycles: int | None = None,
) -> None:
    await asyncio.gather(
        *(
            run_coin_forever(
                coin, client=client_factory(coin), append_fn=append_fn,
                depth_append_fn=depth_append_fn, max_cycles=max_cycles,
            )
            for coin in coins
        )
    )


if __name__ == "__main__":
    asyncio.run(run_forever())
