import asyncio
import datetime as dt
import os

from dotenv import load_dotenv
from nautilus_trader.model.identifiers import InstrumentId

from adapters.data_provider import (
    build_xkrx_equity,
    map_kis_trade_tick,
    parse_kis_trade_message,
)
from backends.kis.ws_auth import get_approval_key
from backends.kis.ws_client import KISWebSocketClient


async def run_stream(
    code: str,
    client: KISWebSocketClient,
    instrument_id: InstrumentId,
    price_precision: int,
    trade_date: dt.date,
    print_fn=print,
) -> None:
    sequence = 0
    async for raw_message in client.stream_trades(code):
        fields = parse_kis_trade_message(raw_message)
        if fields is None:
            continue

        sequence += 1
        tick = map_kis_trade_tick(fields, instrument_id, price_precision, trade_date, sequence)
        print_fn(tick)


def main() -> None:
    load_dotenv()

    code = "005930"
    app_key = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]

    approval_key = get_approval_key(app_key=app_key, app_secret=app_secret)
    client = KISWebSocketClient(approval_key=approval_key)
    instrument = build_xkrx_equity(code)

    asyncio.run(
        run_stream(
            code=code,
            client=client,
            instrument_id=instrument.id,
            price_precision=instrument.price_precision,
            trade_date=dt.date.today(),
        )
    )


if __name__ == "__main__":
    main()
