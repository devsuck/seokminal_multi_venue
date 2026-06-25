import tempfile
from unittest.mock import MagicMock

from nautilus_trader.persistence.catalog import ParquetDataCatalog

from data_ingestion_kospi import run_ingestion_kospi


def test_run_ingestion_kospi_writes_instrument_and_bars_to_catalog():
    client = MagicMock()
    client.get_daily_index_price.return_value = [
        {
            "stck_bsop_date": "20240102",
            "bstp_nmix_oprc": "2645.00",
            "bstp_nmix_hgpr": "2655.00",
            "bstp_nmix_lwpr": "2640.00",
            "bstp_nmix_prpr": "2650.32",
            "acml_vol": "500000000",
        },
        {
            "stck_bsop_date": "20240103",
            "bstp_nmix_oprc": "2651.00",
            "bstp_nmix_hgpr": "2660.00",
            "bstp_nmix_lwpr": "2648.00",
            "bstp_nmix_prpr": "2658.00",
            "acml_vol": "480000000",
        },
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        written = run_ingestion_kospi(
            start="20240101",
            end="20240103",
            catalog_path=tmp_dir,
            client=client,
        )

        assert written == 2

        catalog = ParquetDataCatalog(tmp_dir)
        instruments = catalog.instruments()
        assert len(instruments) == 1
        assert str(instruments[0].id) == "KOSPI.XKRX"

        bars = catalog.bars()
        assert len(bars) == 2
        assert bars[0].close.as_double() == 2650.32
        assert bars[1].close.as_double() == 2658.00

    client.get_daily_index_price.assert_called_once_with("0001", "20240101", "20240103")


def test_run_ingestion_kospi_uses_custom_index_code_override():
    client = MagicMock()
    client.get_daily_index_price.return_value = [
        {
            "stck_bsop_date": "20240102",
            "bstp_nmix_oprc": "2645.00",
            "bstp_nmix_hgpr": "2655.00",
            "bstp_nmix_lwpr": "2640.00",
            "bstp_nmix_prpr": "2650.32",
            "acml_vol": "500000000",
        },
        {
            "stck_bsop_date": "20240103",
            "bstp_nmix_oprc": "2651.00",
            "bstp_nmix_hgpr": "2660.00",
            "bstp_nmix_lwpr": "2648.00",
            "bstp_nmix_prpr": "2658.00",
            "acml_vol": "480000000",
        },
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        written = run_ingestion_kospi(
            start="20240101",
            end="20240103",
            catalog_path=tmp_dir,
            client=client,
            index_code="9999",
        )

        assert written == 2

    client.get_daily_index_price.assert_called_once_with("9999", "20240101", "20240103")
