# tests/test_ib_client.py
import datetime as dt

import pytest
from ib_async.contract import Future
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
    def __init__(self, batches=None, historical_bars=None, contract_details=None):
        self.connect_calls: list[tuple] = []
        self.qualify_calls: list[tuple] = []
        self.contract_details_calls: list[str] = []
        self.req_calls: list[tuple] = []
        self.historical_calls: list[tuple] = []
        self._ticker = FakeTicker(batches if batches is not None else [])
        self._historical_bars = historical_bars if historical_bars is not None else []
        self._contract_details = contract_details or {}

    async def connectAsync(self, host, port, client_id, timeout=4):
        self.connect_calls.append((host, port, client_id))

    async def qualifyContractsAsync(self, contract):
        self.qualify_calls.append((contract.symbol, contract.exchange, contract.currency))
        if contract.symbol not in self._contract_details:
            contract.conId = 1  # 정상 qualify 시뮬레이션(단일 매치)

    async def reqContractDetailsAsync(self, contract):
        self.contract_details_calls.append(contract.symbol)
        return self._contract_details.get(contract.symbol, [])

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


# ── New contract type tests ───────────────────────────────────────────────────

async def test_get_daily_bars_forex_returns_bars():
    bar = BarData(date=dt.date(2025, 1, 2), open=1.09, high=1.095, low=1.088, close=1.092, volume=0.0)
    fake_ib = FakeIB(historical_bars=[bar])
    client = IBClient(ib=fake_ib)
    bars = await client.get_daily_bars_forex("EURUSD", end_date="", duration="1 Y")
    assert bars == [bar]
    assert fake_ib.qualify_calls == [("EUR", "IDEALPRO", "USD")]


async def test_get_daily_bars_forex_raises_on_empty():
    fake_ib = FakeIB(historical_bars=[])
    client = IBClient(ib=fake_ib)
    with pytest.raises(ValueError, match="EURUSD"):
        await client.get_daily_bars_forex("EURUSD", end_date="", duration="1 Y")


async def test_get_daily_bars_forex_uses_midpoint_and_rth_false():
    bar = BarData(date=dt.date(2025, 1, 2), open=1.09, high=1.095, low=1.088, close=1.092, volume=0.0)
    fake_ib = FakeIB(historical_bars=[bar])
    client = IBClient(ib=fake_ib)
    await client.get_daily_bars_forex("EURUSD", end_date="", duration="1 Y")
    # historical_calls tuple: (symbol, exchange, currency, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH)
    assert fake_ib.historical_calls[0][6] == "MIDPOINT"
    assert fake_ib.historical_calls[0][7] is False


async def test_get_daily_bars_future_returns_bars():
    bar = BarData(date=dt.date(2025, 1, 2), open=5900.0, high=5920.0, low=5880.0, close=5910.0, volume=12345.0)
    fake_ib = FakeIB(historical_bars=[bar])
    client = IBClient(ib=fake_ib)
    bars = await client.get_daily_bars_future("ES", "CME", "202509", end_date="", duration="1 Y")
    assert bars == [bar]
    assert fake_ib.qualify_calls == [("ES", "CME", "")]


async def test_get_daily_bars_future_raises_on_empty():
    fake_ib = FakeIB(historical_bars=[])
    client = IBClient(ib=fake_ib)
    with pytest.raises(ValueError, match="ES"):
        await client.get_daily_bars_future("ES", "CME", "202509", end_date="", duration="1 Y")


async def test_get_daily_bars_future_resolves_front_month_when_expiry_omitted():
    """만기월 미지정(expiry="")이면 qualify가 ambiguous로 실패(conId=0) —
    reqContractDetailsAsync 후보 중 만기 지나지 않은 최근월물을 골라 조회해야 한다."""
    bar = BarData(date=dt.date(2025, 1, 2), open=5900.0, high=5920.0, low=5880.0, close=5910.0, volume=12345.0)

    near_expiry = Future(symbol="NQ", exchange="CME", currency="USD")
    near_expiry.conId = 111
    near_expiry.lastTradeDateOrContractMonth = "20260918"

    expired = Future(symbol="NQ", exchange="CME", currency="USD")
    expired.conId = 222
    expired.lastTradeDateOrContractMonth = "20260315"  # 이미 만기 지남 -> 제외돼야 함

    fake_ib = FakeIB(
        historical_bars=[bar],
        contract_details={"NQ": [FakeContractDetails(expired), FakeContractDetails(near_expiry)]},
    )
    client = IBClient(ib=fake_ib)

    bars = await client.get_daily_bars_future("NQ", "CME", "", end_date="", duration="1 Y")

    assert bars == [bar]
    assert fake_ib.contract_details_calls == ["NQ"]
    assert fake_ib.historical_calls[0][0:2] == ("NQ", "CME")


class FakeContractDetails:
    def __init__(self, contract):
        self.contract = contract


async def test_get_daily_bars_option_returns_bars():
    bar = BarData(date=dt.date(2025, 1, 2), open=5.5, high=6.0, low=5.0, close=5.8, volume=500.0)
    fake_ib = FakeIB(historical_bars=[bar])
    client = IBClient(ib=fake_ib)
    bars = await client.get_daily_bars_option("SPY", "20251219", 500.0, "C", end_date="", duration="90 D")
    assert bars == [bar]
    assert fake_ib.qualify_calls == [("SPY", "SMART", "USD")]


async def test_get_daily_bars_option_raises_on_empty():
    fake_ib = FakeIB(historical_bars=[])
    client = IBClient(ib=fake_ib)
    with pytest.raises(ValueError, match="SPY"):
        await client.get_daily_bars_option("SPY", "20251219", 500.0, "C", end_date="", duration="90 D")


async def test_get_daily_bars_crypto_returns_bars():
    bar = BarData(date=dt.date(2025, 1, 2), open=94000.0, high=95500.0, low=93000.0, close=95000.0, volume=1234.5)
    fake_ib = FakeIB(historical_bars=[bar])
    client = IBClient(ib=fake_ib)
    bars = await client.get_daily_bars_crypto("BTC", end_date="", duration="1 Y")
    assert bars == [bar]
    assert fake_ib.qualify_calls == [("BTC", "PAXOS", "USD")]


async def test_get_daily_bars_crypto_uses_rth_false():
    bar = BarData(date=dt.date(2025, 1, 2), open=94000.0, high=95500.0, low=93000.0, close=95000.0, volume=1234.5)
    fake_ib = FakeIB(historical_bars=[bar])
    client = IBClient(ib=fake_ib)
    await client.get_daily_bars_crypto("BTC", end_date="", duration="1 Y")
    # historical_calls tuple index 7 is useRTH
    assert fake_ib.historical_calls[0][7] is False
