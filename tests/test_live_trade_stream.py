import datetime as dt

from nautilus_trader.model.identifiers import InstrumentId

from live_trade_stream import run_stream


class FakeStreamingClient:
    def __init__(self, messages: list[str]) -> None:
        self._messages = messages

    async def stream_trades(self, code: str):
        for message in self._messages:
            yield message


def _trade_record(code="005930", time="093354", price="70000", volume="15", side_code="1") -> str:
    fields = ["0"] * 46
    fields[0] = code
    fields[1] = time
    fields[2] = price
    fields[12] = volume
    fields[21] = side_code
    return "^".join(fields)


async def test_run_stream_prints_mapped_ticks_and_skips_non_trade_frames():
    messages = [
        f"0|H0STCNT0|001|{_trade_record(price='70000')}",
        '{"header":{"tr_id":"PINGPONG"}}',
        f"0|H0STCNT0|001|{_trade_record(price='70100')}",
    ]
    client = FakeStreamingClient(messages)
    instrument_id = InstrumentId.from_str("005930.XKRX")
    printed = []

    await run_stream(
        code="005930",
        client=client,
        instrument_id=instrument_id,
        price_precision=0,
        trade_date=dt.date(2024, 6, 3),
        print_fn=printed.append,
    )

    assert len(printed) == 2
    assert printed[0].price.as_double() == 70000.0
    assert printed[1].price.as_double() == 70100.0
