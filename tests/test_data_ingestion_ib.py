import datetime as dt
import tempfile
from unittest.mock import AsyncMock

from ib_async.objects import BarData
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from data_ingestion_ib import run_ingestion_ib


async def test_run_ingestion_ib_writes_instrument_and_bars_to_catalog():
    client = AsyncMock()
    client.get_daily_bars.return_value = [
        BarData(date=dt.date(2024, 1, 2), open=185.5, high=186.5, low=184.0, close=186.0, volume=50000.0),
        BarData(date=dt.date(2024, 1, 3), open=186.0, high=187.0, low=185.0, close=186.8, volume=42000.0),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        written = await run_ingestion_ib(
            symbol="AAPL",
            end_date="20240103 23:59:59",
            duration="1 Y",
            catalog_path=tmp_dir,
            client=client,
        )

        assert written == 2

        catalog = ParquetDataCatalog(tmp_dir)
        instruments = catalog.instruments()
        assert len(instruments) == 1
        assert str(instruments[0].id) == "AAPL.NASDAQ"

        bars = catalog.bars()
        assert len(bars) == 2
        assert bars[0].close.as_double() == 186.0
        assert bars[1].close.as_double() == 186.8

    client.get_daily_bars.assert_called_once_with("AAPL", "20240103 23:59:59", "1 Y")
