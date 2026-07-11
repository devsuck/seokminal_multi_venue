import asyncio

import pytest

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from orderflow.multi_venue_adapter import (
    MultiVenueOrderflowClient,
    _pool_books,
    _pool_levels,
    _round_to_tick,
)


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

    def __init__(self, events, depth_events=()):
        self._events = events
        self._depth_events = depth_events

    def stream(self, coin):
        return self._gen(self._events)

    def stream_depth(self, coin):
        return self._gen(self._depth_events)

    async def _gen(self, events):
        for e in events:
            yield e


class _HangingClient:
    """이벤트 없이 영원히 대기 — 다른 소스가 먼저 죽어도 안 끊긴다는 걸 보이는 대역."""

    def stream(self, coin):
        return self._gen()

    def stream_depth(self, coin):
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


def test_round_to_tick_floors_to_tick_size():
    assert _round_to_tick(100.3, 1.0) == 100.0
    assert _round_to_tick(100.75, 0.25) == 100.75
    assert _round_to_tick(100.9, 0.25) == 100.75


def test_pool_levels_sums_sizes_at_matching_tick_and_sorts_descending():
    levels_by_venue = [
        [OrderBookLevel(price=100.3, size=1.0), OrderBookLevel(price=99.6, size=2.0)],
        [OrderBookLevel(price=100.7, size=3.0)],
    ]
    pooled = _pool_levels(levels_by_venue, tick_size=1.0, reverse=True)
    assert [lvl.price for lvl in pooled] == [100.0, 99.0]
    assert pooled[0].size == pytest.approx(4.0)  # 100.3(1.0) + 100.7(3.0) 둘 다 100.0으로 반올림
    assert pooled[1].size == pytest.approx(2.0)


def test_pool_books_merges_latest_snapshot_per_venue():
    latest_books = {
        "hyperliquid": OrderBookSnapshot(
            symbol="BTC.HL", ts=10.0,
            bids=[OrderBookLevel(price=100.0, size=1.0)],
            asks=[OrderBookLevel(price=101.0, size=1.0)],
        ),
        "binance-depth": OrderBookSnapshot(
            symbol="BTC.HL", ts=12.0,
            bids=[OrderBookLevel(price=100.0, size=2.0)],
            asks=[OrderBookLevel(price=101.0, size=0.5)],
        ),
    }
    pooled = _pool_books("BTC", latest_books, tick_size=1.0)

    assert pooled.symbol == "BTC.HL"
    assert pooled.ts == 12.0  # 참여 소스 중 가장 최신 ts
    assert pooled.bids[0].size == pytest.approx(3.0)  # 1.0(hl) + 2.0(binance)
    assert pooled.asks[0].size == pytest.approx(1.5)  # 1.0(hl) + 0.5(binance)


async def test_stream_emits_pooled_book_as_venue_depth_arrives():
    hl_book = OrderBookSnapshot(
        symbol="BTC.HL", ts=1000.0,
        bids=[OrderBookLevel(price=100.3, size=1.0), OrderBookLevel(price=99.6, size=2.0)],
        asks=[OrderBookLevel(price=101.2, size=0.5)],
    )
    binance_depth_book = OrderBookSnapshot(
        symbol="BTC.HL", ts=1001.0,
        bids=[OrderBookLevel(price=100.7, size=3.0)],
        asks=[OrderBookLevel(price=101.4, size=0.7)],
    )
    okx_depth_book = OrderBookSnapshot(
        symbol="BTC.HL", ts=1002.0,
        bids=[OrderBookLevel(price=100.1, size=0.2)],
        asks=[OrderBookLevel(price=101.9, size=1.0)],
    )

    hl = _FakeClient([hl_book])
    binance = _FakeClient([], depth_events=[binance_depth_book])
    okx = _FakeClient([], depth_events=[okx_depth_book])

    client = MultiVenueOrderflowClient(hl_client=hl, binance_client=binance, okx_client=okx, tick_size=1.0)
    gen = client.stream("BTC")

    books = [await asyncio.wait_for(gen.__anext__(), timeout=1.0) for _ in range(3)]
    await gen.aclose()

    assert all(isinstance(b, OrderBookSnapshot) for b in books)
    fully_pooled = books[-1]  # 세 소스가 모두 반영된 마지막 스냅샷(순서 무관하게 3번째가 완전 병합)

    bid_by_price = {lvl.price: lvl.size for lvl in fully_pooled.bids}
    ask_by_price = {lvl.price: lvl.size for lvl in fully_pooled.asks}

    assert bid_by_price[100.0] == pytest.approx(4.2)  # 100.3(1.0)+100.7(3.0)+100.1(0.2)
    assert bid_by_price[99.0] == pytest.approx(2.0)
    assert ask_by_price[101.0] == pytest.approx(2.2)  # 101.2(0.5)+101.4(0.7)+101.9(1.0)
    assert fully_pooled.bids[0].price == 100.0  # 매수 호가는 내림차순(최우선 호가가 앞)
