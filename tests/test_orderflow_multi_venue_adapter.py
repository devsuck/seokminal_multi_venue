import asyncio

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from orderflow.multi_venue_adapter import MultiVenueOrderflowClient


def _trade(symbol="BTC.HL", side="buy", price=100.0, size=1.0, ts=1000.0):
    return TradeEvent(symbol=symbol, ts=ts, price=price, size=size, side=side)


def _book():
    return OrderBookSnapshot(
        symbol="BTC.HL", ts=1000.0,
        bids=[OrderBookLevel(price=100.0, size=1.0)],
        asks=[OrderBookLevel(price=101.0, size=1.0)],
    )


class _FakeClient:
    """단순 one-shot 스트림 페이크 — 실제 HL/Binance/OKX 어댑터 대역."""

    def __init__(self, events):
        self._events = events

    def stream(self, coin):
        return self._gen()

    async def _gen(self):
        for e in self._events:
            yield e


class _HangingClient:
    """이벤트 없이 영원히 대기 — 다른 소스가 먼저 죽어도 안 끊긴다는 걸 보이는 대역."""

    def stream(self, coin):
        return self._gen()

    async def _gen(self):
        await asyncio.Event().wait()
        yield  # pragma: no cover - never reached


class _FailThenYieldClient:
    def __init__(self, events):
        self._events = events
        self.call_count = 0

    def stream(self, coin):
        self.call_count += 1
        if self.call_count == 1:
            return self._fail()
        return self._gen()

    async def _fail(self):
        raise ConnectionError("boom")
        yield  # pragma: no cover - unreachable, keeps this an async generator

    async def _gen(self):
        for e in self._events:
            yield e


async def test_merges_events_from_all_three_venues():
    hl = _FakeClient([_book(), _trade(side="buy")])
    binance = _FakeClient([_trade(side="sell")])
    okx = _FakeClient([_trade(side="buy", price=101.0)])

    client = MultiVenueOrderflowClient(hl_client=hl, binance_client=binance, okx_client=okx)
    gen = client.stream("BTC")

    events = []
    for _ in range(3):
        events.append(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
    await gen.aclose()

    assert sum(isinstance(e, OrderBookSnapshot) for e in events) == 1
    assert sum(isinstance(e, TradeEvent) for e in events) == 2


async def test_dead_venue_does_not_block_others():
    hl = _HangingClient()
    binance = _HangingClient()
    okx = _FakeClient([_trade(side="buy")])

    client = MultiVenueOrderflowClient(hl_client=hl, binance_client=binance, okx_client=okx)
    gen = client.stream("BTC")

    event = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
    await gen.aclose()

    assert isinstance(event, TradeEvent)


async def test_failed_source_reconnects_and_still_yields(monkeypatch):
    async def no_sleep(_delay):
        pass

    monkeypatch.setattr("orderflow.multi_venue_adapter.asyncio.sleep", no_sleep)

    hl = _FailThenYieldClient([_trade(side="buy")])
    binance = _HangingClient()
    okx = _HangingClient()

    client = MultiVenueOrderflowClient(hl_client=hl, binance_client=binance, okx_client=okx)
    gen = client.stream("BTC")

    event = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
    await gen.aclose()

    assert isinstance(event, TradeEvent)
    assert hl.call_count >= 2  # 1회 실패 후 재연결해서 이벤트 수신(no_sleep이라 재시도 여러 번 가능)
