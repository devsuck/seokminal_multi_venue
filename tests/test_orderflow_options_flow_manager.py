import asyncio
from asyncio import sleep as _real_sleep
from unittest.mock import AsyncMock, patch

from orderflow.deribit_adapter import OptionTradeEvent
from orderflow.options_flow_manager import RECONNECT_BASE_DELAY, OptionsFlowManager


def _trade(instrument_name="BTC-27DEC26-100000-C", direction="buy"):
    return OptionTradeEvent(
        instrument_name=instrument_name, direction=direction, price=0.05,
        amount=10.0, iv=55.0, index_price=65000.0, timestamp=1000.0,
    )


async def _one_shot_stream(events):
    for e in events:
        yield e


async def test_subscribe_starts_worker_and_broadcasts_trade():
    manager = OptionsFlowManager(adapter_factory=lambda currency: _one_shot_stream([_trade()]))
    queue = manager.subscribe("BTC")
    assert manager.active_currencies() == ["BTC"]

    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert msg == {
        "type": "trade",
        "instrument_name": "BTC-27DEC26-100000-C",
        "direction": "buy",
        "price": 0.05,
        "amount": 10.0,
        "iv": 55.0,
        "index_price": 65000.0,
        "timestamp": 1000.0,
    }

    manager.unsubscribe("BTC", queue)
    assert manager.active_currencies() == []


async def test_subscribe_currency_is_case_insensitive():
    manager = OptionsFlowManager(adapter_factory=lambda currency: _one_shot_stream([]))
    manager.subscribe("btc")
    assert manager.active_currencies() == ["BTC"]


async def test_second_subscriber_reuses_worker():
    manager = OptionsFlowManager(adapter_factory=lambda currency: _one_shot_stream([]))
    q1 = manager.subscribe("ETH")
    q2 = manager.subscribe("ETH")
    assert manager.active_currencies() == ["ETH"]
    manager.unsubscribe("ETH", q1)
    assert manager.active_currencies() == ["ETH"]  # q2 아직 구독 중 -> worker 유지
    manager.unsubscribe("ETH", q2)
    assert manager.active_currencies() == []


async def test_reconnects_with_backoff_then_broadcasts_live_before_trade():
    call_count = 0

    async def flaky(currency):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("boom")
        yield _trade()

    manager = OptionsFlowManager(adapter_factory=flaky)

    async def mock_sleep(delay):
        await _real_sleep(0.001)

    with patch("orderflow.options_flow_manager.asyncio.sleep", new=AsyncMock(side_effect=mock_sleep)) as mock_sleep_obj:
        queue = manager.subscribe("BTC")
        reconnecting_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        live_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        trade_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        manager.unsubscribe("BTC", queue)

    assert reconnecting_msg == {"type": "status", "state": "reconnecting"}
    assert live_msg == {"type": "status", "state": "live"}
    assert trade_msg["type"] == "trade"
    mock_sleep_obj.assert_any_call(RECONNECT_BASE_DELAY)


async def test_put_drops_oldest_message_when_queue_full():
    manager = OptionsFlowManager(adapter_factory=lambda currency: _one_shot_stream([]))
    queue: asyncio.Queue = asyncio.Queue(maxsize=2)

    manager._put(queue, {"seq": 1})
    manager._put(queue, {"seq": 2})
    assert queue.full()

    manager._put(queue, {"seq": 3})

    assert queue.qsize() == 2
    remaining = [queue.get_nowait(), queue.get_nowait()]
    assert remaining == [{"seq": 2}, {"seq": 3}]
