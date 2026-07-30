import asyncio
from asyncio import sleep as _real_sleep
from unittest.mock import AsyncMock, patch

from orderflow.manager import RECONNECT_BASE_DELAY, OrderflowManager
from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent


def _trade(price=100.0, size=1.0, side="buy", ts=1000.0, symbol="BTC.HL"):
    return TradeEvent(symbol=symbol, ts=ts, price=price, size=size, side=side)


def _book(ts=1000.0, symbol="BTC.HL"):
    return OrderBookSnapshot(
        symbol=symbol,
        ts=ts,
        bids=[OrderBookLevel(price=100.0, size=1.0)],
        asks=[OrderBookLevel(price=101.0, size=1.0)],
    )


async def _one_shot_stream(events):
    for e in events:
        yield e


async def test_subscribe_starts_worker_and_broadcasts_delta():
    manager = OrderflowManager(adapter_factory=lambda symbol: _one_shot_stream([_trade()]))
    queue, snapshot = manager.subscribe("BTC.HL")
    assert snapshot == {"footprint": [], "heatmap": []}
    assert manager.active_symbols() == ["BTC.HL"]

    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert msg["type"] == "footprint_delta"
    assert msg["side"] == "buy"

    manager.unsubscribe("BTC.HL", queue)
    assert manager.active_symbols() == []


async def test_second_subscriber_reuses_worker_and_gets_same_snapshot():
    manager = OrderflowManager(adapter_factory=lambda symbol: _one_shot_stream([]))
    queue1, _ = manager.subscribe("NQ")
    queue2, _ = manager.subscribe("NQ")
    assert manager.active_symbols() == ["NQ"]
    manager.unsubscribe("NQ", queue1)
    assert manager.active_symbols() == ["NQ"]  # queue2 아직 구독 중 -> worker 유지
    manager.unsubscribe("NQ", queue2)
    assert manager.active_symbols() == []


async def test_reconnects_with_backoff_then_broadcasts_live_before_delta():
    call_count = 0

    async def flaky(symbol):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("boom")
        yield _trade()

    manager = OrderflowManager(adapter_factory=flaky)

    # Mock sleep to yield control but still track the call
    async def mock_sleep(delay):
        await _real_sleep(0.001)

    with patch("orderflow.manager.asyncio.sleep", new=AsyncMock(side_effect=mock_sleep)) as mock_sleep_obj:
        queue, _ = manager.subscribe("NQ")
        reconnecting_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        live_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        delta_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        manager.unsubscribe("NQ", queue)

    assert reconnecting_msg == {"type": "status", "state": "reconnecting"}
    assert live_msg == {"type": "status", "state": "live"}
    assert delta_msg["type"] == "footprint_delta"
    mock_sleep_obj.assert_any_call(RECONNECT_BASE_DELAY)


async def test_put_drops_oldest_message_when_queue_full():
    manager = OrderflowManager(adapter_factory=lambda symbol: _one_shot_stream([]))
    queue: asyncio.Queue = asyncio.Queue(maxsize=2)

    manager._put(queue, {"seq": 1})
    manager._put(queue, {"seq": 2})
    assert queue.full()

    manager._put(queue, {"seq": 3})

    assert queue.qsize() == 2
    remaining = [queue.get_nowait(), queue.get_nowait()]
    assert remaining == [{"seq": 2}, {"seq": 3}]


async def test_book_snapshot_broadcast_on_first_book_event():
    manager = OrderflowManager(adapter_factory=lambda symbol: _one_shot_stream([_book(ts=1000.0)]))
    queue, _ = manager.subscribe("BTC.HL")

    msgs = []
    for _ in range(2):
        msgs.append(await asyncio.wait_for(queue.get(), timeout=1.0))
    types = {m["type"] for m in msgs}
    assert "book_snapshot" in types
    book_msg = next(m for m in msgs if m["type"] == "book_snapshot")
    assert book_msg["bids"] == [{"price": 100.0, "size": 1.0}]
    assert book_msg["asks"] == [{"price": 101.0, "size": 1.0}]

    manager.unsubscribe("BTC.HL", queue)


async def test_book_snapshot_throttled_within_150ms_window():
    clock = {"t": 1000.0}

    def now_fn():
        return clock["t"]

    manager = OrderflowManager(
        adapter_factory=lambda symbol: _one_shot_stream([_book(ts=1000.0), _book(ts=1000.05)]),
        now_fn=now_fn,
    )
    queue, _ = manager.subscribe("BTC.HL")

    msgs = []
    try:
        while True:
            msgs.append(await asyncio.wait_for(queue.get(), timeout=0.2))
    except asyncio.TimeoutError:
        pass

    book_msgs = [m for m in msgs if m["type"] == "book_snapshot"]
    assert len(book_msgs) == 1  # 두 번째 이벤트는 150ms 이내라 스로틀됨(now_fn이 고정이므로)

    manager.unsubscribe("BTC.HL", queue)


def _book_with_bid_size(ts, size):
    return OrderBookSnapshot(
        symbol="BTC.HL", ts=ts,
        bids=[OrderBookLevel(price=100.0, size=size)],
        # ask는 tick_size=10(BTC.HL)로 라운딩되는 bid(100.0)와 같은 버킷에 안 걸리게 200.0으로 뗀다.
        # 101.0을 쓰면 라운딩 후 100.0으로 같이 뭉쳐서 pending_heatmap 키가 충돌해 서로 덮어씀.
        asks=[OrderBookLevel(price=200.0, size=1.0)],
    )


async def test_heatmap_delta_coalesced_within_throttle_window():
    """book_snapshot과 별개로 스로틀 없이 매 틱 나가던 heatmap_delta가 발열 원인이었음(실측 61.5/sec) —
    같은 150ms 창에 묶어 키별 최신값만 방출하는지 확인.
    1틱째는 book_snapshot과 동일 규칙(최초 이벤트는 즉시 flush)으로 단독 방출되고,
    2·3틱째는 같은 창 안이라 pending에 쌓였다가 4틱째(창 경과, now_fn 수동 전진)에 합쳐져 나간다."""
    clock = {"t": 1000.0}

    def now_fn():
        return clock["t"]

    events = [
        _book_with_bid_size(1000.0, 1.0),
        _book_with_bid_size(1000.0, 2.0),
        _book_with_bid_size(1000.0, 3.0),
        _book_with_bid_size(1000.2, 3.0),
    ]
    call_count = {"n": 0}

    async def stream(symbol):
        for e in events:
            call_count["n"] += 1
            if call_count["n"] == 4:
                clock["t"] = 1000.2
            yield e

    manager = OrderflowManager(adapter_factory=stream, now_fn=now_fn)
    queue, _ = manager.subscribe("BTC.HL")

    msgs = []
    try:
        while True:
            msgs.append(await asyncio.wait_for(queue.get(), timeout=0.2))
    except asyncio.TimeoutError:
        pass

    heatmap_msgs = [m for m in msgs if m["type"] == "heatmap_delta" and m["price"] == 100.0]
    # 2,3틱(size 2.0, 3.0)은 같은 창 안이라 한 번에 3.0으로만 나가고 2.0은 안 나감
    assert [m["size"] for m in heatmap_msgs] == [1.0, 3.0]

    manager.unsubscribe("BTC.HL", queue)


async def test_heatmap_delta_flushes_again_after_throttle_window_elapses():
    clock = {"t": 1000.0}

    def now_fn():
        return clock["t"]

    events = [_book_with_bid_size(1000.0, 1.0), _book_with_bid_size(1000.2, 2.0)]
    call_count = {"n": 0}

    async def stream(symbol):
        for e in events:
            call_count["n"] += 1
            if call_count["n"] == 2:
                clock["t"] = 1000.2
            yield e

    manager = OrderflowManager(adapter_factory=stream, now_fn=now_fn)
    queue, _ = manager.subscribe("BTC.HL")

    msgs = []
    try:
        while True:
            msgs.append(await asyncio.wait_for(queue.get(), timeout=0.2))
    except asyncio.TimeoutError:
        pass

    heatmap_msgs = [m for m in msgs if m["type"] == "heatmap_delta" and m["price"] == 100.0]
    assert [m["size"] for m in heatmap_msgs] == [1.0, 2.0]

    manager.unsubscribe("BTC.HL", queue)


async def test_book_snapshot_broadcast_again_after_throttle_window_elapses():
    clock = {"t": 1000.0}

    def now_fn():
        return clock["t"]

    events = [_book(ts=1000.0), _book(ts=1000.2)]
    call_count = {"n": 0}

    async def stream(symbol):
        for e in events:
            call_count["n"] += 1
            if call_count["n"] == 2:
                clock["t"] = 1000.2  # 150ms 스로틀 윈도우 경과 시뮬레이션
            yield e

    manager = OrderflowManager(adapter_factory=stream, now_fn=now_fn)
    queue, _ = manager.subscribe("BTC.HL")

    msgs = []
    try:
        while True:
            msgs.append(await asyncio.wait_for(queue.get(), timeout=0.2))
    except asyncio.TimeoutError:
        pass

    book_msgs = [m for m in msgs if m["type"] == "book_snapshot"]
    assert len(book_msgs) == 2

    manager.unsubscribe("BTC.HL", queue)
