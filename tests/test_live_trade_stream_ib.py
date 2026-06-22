import datetime as dt

from nautilus_trader.model.identifiers import InstrumentId

from live_trade_stream_ib import run_stream


class FakeRawTick:
    def __init__(self, time, price, size):
        self.time = time
        self.price = price
        self.size = size


class FakeIBClient:
    def __init__(self, ticks: list) -> None:
        self._ticks = ticks

    async def stream_trades(self, symbol: str):
        for tick in self._ticks:
            yield tick


async def test_run_stream_prints_mapped_ticks():
    ticks = [
        FakeRawTick(dt.datetime(2024, 6, 3, 13, 30, 0, tzinfo=dt.timezone.utc), 195.50, 100),
        FakeRawTick(dt.datetime(2024, 6, 3, 13, 30, 1, tzinfo=dt.timezone.utc), 195.55, 50),
    ]
    client = FakeIBClient(ticks)
    instrument_id = InstrumentId.from_str("AAPL.NASDAQ")
    printed = []

    await run_stream(
        symbol="AAPL",
        client=client,
        instrument_id=instrument_id,
        price_precision=2,
        print_fn=printed.append,
    )

    assert len(printed) == 2
    assert printed[0].price.as_double() == 195.50
    assert printed[1].price.as_double() == 195.55
