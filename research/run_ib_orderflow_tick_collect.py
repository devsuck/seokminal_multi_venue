"""IB 오더플로우 틱+뎁스 수집기 — tmux로 상시 실행.

NQ/MNQ footprint/heatmap 신호 백테스트용 원시 데이터 축적이 목적. raw tick을
저장하지 않고 라이브 대시보드와 동일한 OrderflowAggregator를 통과시켜 나온
footprint_delta/heatmap_delta만 저장한다 — 연구용 신호 재구성이 라이브 렌더링과
동일 소스코드 기반이 되어, 백테스트 로직이 프론트 로직과 슬쩍 달라지는 버그
클래스를 원천 차단한다. 심볼별로 독립된 재연결 루프를 돌려 한쪽 스트림이 끊겨도
다른 심볼 수집에 영향 없다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path

from orderflow.aggregator import OrderflowAggregator
from orderflow.ib_adapter import IBOrderflowClient
from orderflow.models import OrderBookSnapshot, TradeEvent

_DATA_DIR = Path("research/data/ib_orderflow_tick")

SYMBOLS = ["NQ", "MNQ"]
# 기존 라이브 client_id(1=데이터/2=주문, live_engine/ib_broker.py)와 오더플로우
# 기본값(20, orderflow/ib_adapter.py)에 안 겹치게 심볼별로 분리 — NQ+MNQ 동시 수집 시
# 같은 client_id를 재사용하면 IB Gateway 접속이 충돌한다(2026-07 client_id 충돌 버그와 동일 원인).
CLIENT_IDS = {"NQ": 20, "MNQ": 21}
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0
TICK_SIZE = 0.25  # CME NQ/MNQ 표준 틱


def append_deltas(symbol: str, deltas: list[dict]) -> None:
    if not deltas:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{symbol}_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for d in deltas:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


async def run_symbol_forever(
    symbol: str,
    *,
    client: IBOrderflowClient | None = None,
    append_fn=append_deltas,
    max_cycles: int | None = None,
) -> None:
    client = client or IBOrderflowClient(client_id=CLIENT_IDS[symbol])
    aggregator = OrderflowAggregator(tick_size=TICK_SIZE)
    cycle = 0
    delay = RECONNECT_BASE_DELAY
    while max_cycles is None or cycle < max_cycles:
        received_event = False
        try:
            async for event in client.stream(symbol):
                if isinstance(event, TradeEvent):
                    received_event = True
                    append_fn(symbol, [aggregator.on_trade(event)])
                elif isinstance(event, OrderBookSnapshot):
                    received_event = True
                    deltas = aggregator.on_book_snapshot(event)
                    if deltas:
                        append_fn(symbol, deltas)
            if received_event:
                # 정상적으로 이벤트를 수신하다 스트림이 종료된 경우 — 백오프 불필요
                delay = RECONNECT_BASE_DELAY
            else:
                # 구독 직후 이벤트 하나 없이 스트림이 끊긴 경우 — 반복되면 핫루프가 되므로
                # 예외 케이스와 동일하게 백오프 적용
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
        except Exception:
            logging.exception("IB orderflow stream failed for %s, reconnecting", symbol)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        cycle += 1


async def run_forever(
    *,
    symbols: list[str] = SYMBOLS,
    client_factory=lambda symbol: IBOrderflowClient(client_id=CLIENT_IDS[symbol]),
    append_fn=append_deltas,
    max_cycles: int | None = None,
) -> None:
    await asyncio.gather(
        *(
            run_symbol_forever(symbol, client=client_factory(symbol), append_fn=append_fn, max_cycles=max_cycles)
            for symbol in symbols
        )
    )


if __name__ == "__main__":
    asyncio.run(run_forever())
