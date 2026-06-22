import datetime as dt

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
    def __init__(self, batches):
        self.connect_calls: list[tuple] = []
        self.qualify_calls: list[tuple] = []
        self.req_calls: list[tuple] = []
        self._ticker = FakeTicker(batches)

    async def connectAsync(self, host, port, client_id):
        self.connect_calls.append((host, port, client_id))

    async def qualifyContractsAsync(self, contract):
        self.qualify_calls.append((contract.symbol, contract.exchange, contract.currency))

    def reqTickByTickData(self, contract, tick_type):
        self.req_calls.append((contract.symbol, contract.exchange, contract.currency, tick_type))
        return self._ticker


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
