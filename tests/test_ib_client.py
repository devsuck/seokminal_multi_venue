# tests/test_ib_client.py
import datetime as dt

import pytest
from ib_async.objects import BarData

from backends.ib.client import IBClient


class FakeTickByTick:
    def __init__(self, time, price, size):
        self.time = time
        self.price = price
        self.size = size


class FakeUpdateEvent:
    def __init__(self, ticker, batches):
        self._ticker = ticker
        self._batches = batches

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for batch in self._batches:
            self._ticker.tickByTicks = list(batch)
            yield self._ticker


class FakeTicker:
    def __init__(self, batches):
        self.tickByTicks: list = []
        self.updateEvent = FakeUpdateEvent(self, batches)


class FakeIB:
    def __init__(self, batches=None, historical_bars=None):
        self.connect_calls: list[tuple] = []
        self.qualify_calls: list[tuple] = []
        self.req_calls: list[tuple] = []
        self.historical_calls: list[tuple] = []
        self._ticker = FakeTicker(batches if batches is not None else [])
        self._historical_bars = historical_bars if historical_bars is not None else []

    async def connectAsync(self, host, port, client_id):
        self.connect_calls.append((host, port, client_id))

    async def qualifyContractsAsync(self, contract):
        self.qualify_calls.append((contract.symbol, contract.exchange, contract.currency))

    def reqTickByTickData(self, contract, tick_type):
        self.req_calls.append((contract.symbol, contract.exchange, contract.currency, tick_type))
        return self._ticker

    async def reqHistoricalDataAsync(
        self, contract, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH
    ):
        self.historical_calls.append(
            (
                contract.symbol,
                contract.exchange,
                contract.currency,
                endDateTime,
                durationStr,
                barSizeSetting,
                whatToShow,
                useRTH,
            )
        )
        return self._historical_bars


async def test_stream_trades_connects_subscribes_and_yields_ticks():
    tick1 = FakeTickByTick(dt.datetime(2024, 6, 3, 13, 30, 0, tzinfo=dt.timezone.utc), 195.50, 100)
    tick2 = FakeTickByTick(dt.datetime(2024, 6, 3, 13, 30, 1, tzinfo=dt.timezone.utc), 195.55, 50)
    fake_ib = FakeIB(batches=[[tick1], [tick2]])
    client = IBClient(host="127.0.0.1", port=7497, client_id=1, ib=fake_ib)

    received = []
    async for tick in client.stream_trades("AAPL"):
        received.append(tick)

    assert received == [tick1, tick2]
    assert fake_ib.connect_calls == [("127.0.0.1", 7497, 1)]
    assert fake_ib.qualify_calls == [("AAPL", "SMART", "USD")]
    assert fake_ib.req_calls == [("AAPL", "SMART", "USD", "AllLast")]


async def test_get_daily_bars_connects_subscribes_and_returns_bars():
    bar = BarData(date=dt.date(2024, 1, 2), open=185.5, high=186.5, low=184.0, close=186.0, volume=50000.0)
    fake_ib = FakeIB(historical_bars=[bar])
    client = IBClient(host="127.0.0.1", port=7497, client_id=1, ib=fake_ib)

    bars = await client.get_daily_bars("AAPL", end_date="20240601 23:59:59", duration="1 Y")

    assert bars == [bar]
    assert fake_ib.connect_calls == [("127.0.0.1", 7497, 1)]
    assert fake_ib.qualify_calls == [("AAPL", "SMART", "USD")]
    assert fake_ib.historical_calls == [
        ("AAPL", "SMART", "USD", "20240601 23:59:59", "1 Y", "1 day", "TRADES", True)
    ]


async def test_get_daily_bars_raises_value_error_on_empty_response():
    fake_ib = FakeIB(historical_bars=[])
    client = IBClient(host="127.0.0.1", port=7497, client_id=1, ib=fake_ib)

    with pytest.raises(ValueError, match="AAPL"):
        await client.get_daily_bars("AAPL", end_date="", duration="1 Y")
