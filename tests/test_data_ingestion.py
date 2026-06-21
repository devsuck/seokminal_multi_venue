import tempfile
from unittest.mock import MagicMock

from nautilus_trader.persistence.catalog import ParquetDataCatalog

from data_ingestion import run_ingestion


def test_run_ingestion_writes_instrument_and_bars_to_catalog():
    client = MagicMock()
    client.get_daily_price.return_value = [
        {
            "stck_bsop_date": "20240102",
            "stck_oprc": "69500",
            "stck_hgpr": "70500",
            "stck_lwpr": "69000",
            "stck_clpr": "70000",
            "acml_vol": "1000000",
        },
        {
            "stck_bsop_date": "20240103",
            "stck_oprc": "70000",
            "stck_hgpr": "71000",
            "stck_lwpr": "69800",
            "stck_clpr": "70800",
            "acml_vol": "900000",
        },
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        written = run_ingestion(
            code="005930",
            start="20240101",
            end="20240103",
            catalog_path=tmp_dir,
            client=client,
        )

        assert written == 2

        catalog = ParquetDataCatalog(tmp_dir)
        instruments = catalog.instruments()
        assert len(instruments) == 1
        assert str(instruments[0].id) == "005930.XKRX"

        bars = catalog.bars()
        assert len(bars) == 2
        assert bars[0].close.as_double() == 70000.0
        assert bars[1].close.as_double() == 70800.0

    client.get_daily_price.assert_called_once_with("005930", "20240101", "20240103")
