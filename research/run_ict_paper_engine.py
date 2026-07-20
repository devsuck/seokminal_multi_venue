"""BTC.HL ICT+오더플로우 페이퍼 엔진 진입점 — 상시 프로세스.

CLI: PYTHONPATH=. python3 research/run_ict_paper_engine.py
tmux 상시구동: tmux new -s ict-orderflow-paper 'PYTHONPATH=. python3 research/run_ict_paper_engine.py'
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

from orderflow.hl_adapter import HyperliquidOrderflowClient
from orderflow.models import OrderBookSnapshot, TradeEvent
from research.ict.paper.htf_zones import fetch_htf_bars
from research.ict.paper.reversal_triggers import LTFBarBuilder
from research.ict.paper.state_machine import PaperEngine

COIN = "BTC"
HTF_POLL_SEC = 900.0  # 15분
STATE_PATH = "research/data/ict_paper_state.json"
JOURNAL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "seokminal-dashboard", "docs", "orderflow-journal.csv"
)


async def _poll_htf(
    engine: PaperEngine,
    fetch_fn: Callable[[str, str, int], list[dict]] = fetch_htf_bars,
    poll_sec: float = HTF_POLL_SEC,
) -> None:
    while True:
        try:
            bars = fetch_fn(COIN, "15m", 100)
            for bar in bars:
                engine.on_htf_bar(bar)
        except Exception:
            logging.exception("HTF 폴링 실패 — 이번 사이클 스킵")
        await asyncio.sleep(poll_sec)


async def _stream_ltf(engine: PaperEngine, client: HyperliquidOrderflowClient) -> None:
    bar_builder = LTFBarBuilder()
    async for event in client.stream(COIN):
        if isinstance(event, TradeEvent):
            result = bar_builder.on_trade(event)
            if result is not None:
                engine.on_ltf_bar(result)
            engine.on_price_tick(event.price)
        elif isinstance(event, OrderBookSnapshot) and event.bids and event.asks:
            mid = (event.bids[0].price + event.asks[0].price) / 2.0
            engine.on_price_tick(mid)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = PaperEngine(symbol=f"{COIN}.HL", state_path=STATE_PATH, journal_path=JOURNAL_PATH)
    client = HyperliquidOrderflowClient()
    await asyncio.gather(_poll_htf(engine), _stream_ltf(engine, client))


if __name__ == "__main__":
    asyncio.run(main())
