import asyncio

import pytest

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from research.ict.paper.state_machine import PaperEngine
from research.run_ict_paper_engine import _poll_htf, _stream_ltf


class FakeHLClient:
    def __init__(self, events: list):
        self._events = events
        self.n_calls = 0

    async def stream(self, coin: str):
        self.n_calls += 1
        for e in self._events:
            yield e


async def test_stream_ltf_consumes_events_then_reconnects_when_stream_ends(tmp_path):
    """실제 HL 어댑터는 연결이 끊기면 예외 없이 조용히 끝난다(정상 StopAsyncIteration) —
    바깥 루프가 이를 '재연결 필요'로 취급하지 않으면 LTF 스트림이 영구 정지한다
    (2026-08-02, ict-orderflow-paper 프로세스 실측: lsof 소켓 0개, 재연결 로직 부재가 원인)."""
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
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            _stream_ltf(engine, client, initial_backoff_s=0.01, max_backoff_s=0.01), timeout=0.05
        )
    assert client.n_calls >= 2  # 스트림 정상 종료 후에도 재연결 시도했어야 함


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
