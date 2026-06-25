import argparse
import asyncio
import datetime as dt

from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for, build_us_equity, map_ib_daily_bar
from backends.ib.client import IBClient


async def run_ingestion_ib(
    symbol: str, end_date: str, duration: str, catalog_path: str, client: IBClient,
    venue: str = "NASDAQ",
) -> int:
    instrument = build_us_equity(symbol, venue=venue)
    bar_type = bar_type_for(instrument.id)

    rows = await client.get_daily_bars(symbol, end_date, duration)
    bars = [map_ib_daily_bar(row, bar_type, instrument.price_precision) for row in rows]

    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([instrument])
    catalog.write_data(bars)

    return len(bars)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest IB daily bars into a ParquetDataCatalog")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--venue", default="NASDAQ")
    parser.add_argument("--end-date", default=dt.date.today().strftime("%Y%m%d 23:59:59"))
    parser.add_argument("--duration", default="1 Y")
    parser.add_argument("--catalog-path", default="./catalog")
    args = parser.parse_args()

    client = IBClient()

    written = asyncio.run(
        run_ingestion_ib(args.symbol, args.end_date, args.duration, args.catalog_path, client, venue=args.venue)
    )
    print(
        f"Wrote {written} bars for {args.symbol} "
        f"(duration={args.duration}, end={args.end_date}) to {args.catalog_path}"
    )


if __name__ == "__main__":
    main()
