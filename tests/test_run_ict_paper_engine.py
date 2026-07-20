import asyncio

import pytest

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from research.ict.paper.state_machine import PaperEngine
from research.run_ict_paper_engine import _poll_htf, _stream_ltf


class FakeHLClient:
    def __init__(self, events: list):
        self._events = events

    async def stream(self, coin: str):
        for e in self._events:
            yield e


async def test_stream_ltf_consumes_trades_and_book_snapshots_without_error(tmp_path):
    engine = PaperEngine(
        symbol="BTC.HL", state_path=str(tmp_path / "s.json"), journal_path=str(tmp_path / "j.csv")
    )
    events = [
        TradeEvent(symbol="BTC.HL", ts=0.0, price=100.0, size=1.0, side="buy"),
        OrderBookSnapshot(
            symbol="BTC.HL", ts=1.0,
            bids=[OrderBookLevel(price=99.5, size=1.0)],
            asks=[OrderBookLevel(price=100.5, size=1.0)],
        ),
    ]
    client = FakeHLClient(events)
    await _stream_ltf(engine, client)  # 예외 없이 전체 스트림 소비하면 통과(와이어링 스모크)


async def test_poll_htf_calls_fetch_fn_and_feeds_engine(tmp_path):
    engine = PaperEngine(
        symbol="BTC.HL", state_path=str(tmp_path / "s.json"), journal_path=str(tmp_path / "j.csv")
    )
    calls = {"n": 0}

    def fake_fetch(coin: str, interval: str, bars: int) -> list[dict]:
        calls["n"] += 1
        return [{"ts": 0, "open": 100, "high": 101, "low": 99, "close": 100.5}]

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_poll_htf(engine, fetch_fn=fake_fetch, poll_sec=0.01), timeout=0.03)

    assert calls["n"] >= 1
