import argparse
import datetime as dt
import os

from dotenv import load_dotenv
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for, build_kospi_index, map_kis_index_daily_bar
from backends.kis.client import KISClient

KOSPI_INDEX_CODE = "0001"


def run_ingestion_kospi(start: str, end: str, catalog_path: str, client: KISClient) -> int:
    instrument = build_kospi_index()
    bar_type = bar_type_for(instrument.id)

    rows = client.get_daily_index_price(KOSPI_INDEX_CODE, start, end)
    bars = [
        map_kis_index_daily_bar(row, bar_type, instrument.price_precision)
        for row in rows
    ]

    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([instrument])
    catalog.write_data(bars)

    return len(bars)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Ingest KOSPI daily index bars into a ParquetDataCatalog")
    parser.add_argument("--index-code", default=KOSPI_INDEX_CODE)
    parser.add_argument("--start", default=(dt.date.today() - dt.timedelta(days=365)).strftime("%Y%m%d"))
    parser.add_argument("--end", default=dt.date.today().strftime("%Y%m%d"))
    parser.add_argument("--catalog-path", default="./catalog")
    args = parser.parse_args()

    app_key = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    client = KISClient(app_key=app_key, app_secret=app_secret)

    written = run_ingestion_kospi(args.start, args.end, args.catalog_path, client)
    print(f"Wrote {written} bars for KOSPI ({args.start}-{args.end}) to {args.catalog_path}")


if __name__ == "__main__":
    main()
