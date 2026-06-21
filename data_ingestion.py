import argparse
import datetime as dt
import os

from dotenv import load_dotenv
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for, build_xkrx_equity, map_kis_daily_bar
from backends.kis.client import KISClient


def run_ingestion(code: str, start: str, end: str, catalog_path: str, client: KISClient) -> int:
    instrument = build_xkrx_equity(code)
    bar_type = bar_type_for(instrument.id)

    rows = client.get_daily_price(code, start, end)
    bars = [
        map_kis_daily_bar(row, bar_type, instrument.price_precision)
        for row in rows
    ]

    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([instrument])
    catalog.write_data(bars)

    return len(bars)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Ingest KIS daily bars into a ParquetDataCatalog")
    parser.add_argument("--code", default="005930")
    parser.add_argument("--start", default=(dt.date.today() - dt.timedelta(days=365)).strftime("%Y%m%d"))
    parser.add_argument("--end", default=dt.date.today().strftime("%Y%m%d"))
    parser.add_argument("--catalog-path", default="./catalog")
    args = parser.parse_args()

    app_key = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    client = KISClient(app_key=app_key, app_secret=app_secret)

    written = run_ingestion(args.code, args.start, args.end, args.catalog_path, client)
    print(f"Wrote {written} bars for {args.code} ({args.start}-{args.end}) to {args.catalog_path}")


if __name__ == "__main__":
    main()
