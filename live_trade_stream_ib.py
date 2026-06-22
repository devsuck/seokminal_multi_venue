import asyncio

from nautilus_trader.model.identifiers import InstrumentId

from adapters.data_provider import build_us_equity, map_ib_trade_tick
from backends.ib.client import IBClient


async def run_stream(
    symbol: str,
    client: IBClient,
    instrument_id: InstrumentId,
    price_precision: int,
    print_fn=print,
) -> None:
    sequence = 0
    async for raw_tick in client.stream_trades(symbol):
        sequence += 1
        tick = map_ib_trade_tick(raw_tick, instrument_id, price_precision, sequence)
        print_fn(tick)


def main() -> None:
    symbol = "AAPL"
    equity = build_us_equity(symbol)
    client = IBClient()

    asyncio.run(
        run_stream(
            symbol=symbol,
            client=client,
            instrument_id=equity.id,
            price_precision=equity.price_precision,
        )
    )


if __name__ == "__main__":
    main()
