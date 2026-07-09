import asyncio
from asyncio import sleep as _real_sleep
from unittest.mock import AsyncMock, patch

from orderflow.manager import RECONNECT_BASE_DELAY, OrderflowManager
from orderflow.models import TradeEvent


def _trade(price=100.0, size=1.0, side="buy", ts=1000.0, symbol="BTC.HL"):
    return TradeEvent(symbol=symbol, ts=ts, price=price, size=size, side=side)


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
