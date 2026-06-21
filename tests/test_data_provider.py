from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

from adapters.data_provider import bar_type_for, build_xkrx_equity, map_kis_daily_bar


def test_build_xkrx_equity_has_expected_fields():
    equity = build_xkrx_equity("005930")

    assert equity.id == InstrumentId.from_str("005930.XKRX")
    assert str(equity.quote_currency) == "KRW"
    assert equity.price_precision == 0
    assert equity.lot_size.as_double() == 1.0


def test_bar_type_for_builds_daily_external_bar_type():
    instrument_id = InstrumentId.from_str("005930.XKRX")

    bar_type = bar_type_for(instrument_id)

    assert bar_type == BarType.from_str("005930.XKRX-1-DAY-LAST-EXTERNAL")


def test_map_kis_daily_bar_converts_row_to_bar():
    bar_type = bar_type_for(InstrumentId.from_str("005930.XKRX"))
    row = {
        "stck_bsop_date": "20240102",
        "stck_oprc": "69500",
        "stck_hgpr": "70500",
        "stck_lwpr": "69000",
        "stck_clpr": "70000",
        "acml_vol": "1000000",
    }

    bar = map_kis_daily_bar(row, bar_type, price_precision=0)

    assert bar.bar_type == bar_type
    assert bar.open.as_double() == 69500.0
    assert bar.high.as_double() == 70500.0
    assert bar.low.as_double() == 69000.0
    assert bar.close.as_double() == 70000.0
    assert bar.volume.as_double() == 1_000_000.0
    # 2024-01-02 00:00:00 UTC in nanoseconds
    assert bar.ts_event == 1704153600000000000
