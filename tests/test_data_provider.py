import datetime as dt
from types import SimpleNamespace

from ib_async.objects import BarData
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import IndexInstrument

from adapters.data_provider import (
    bar_type_for,
    build_kospi_index,
    build_us_equity,
    build_xkrx_equity,
    map_ib_daily_bar,
    map_ib_trade_tick,
    map_kis_daily_bar,
    map_kis_index_daily_bar,
    map_kis_trade_tick,
    parse_kis_trade_message,
)


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


def test_map_ib_daily_bar_converts_row_to_bar():
    bar_type = bar_type_for(InstrumentId.from_str("AAPL.NASDAQ"))
    row = BarData(
        date=dt.date(2024, 1, 2),
        open=185.5,
        high=186.5,
        low=184.0,
        close=186.0,
        volume=50000.0,
    )

    bar = map_ib_daily_bar(row, bar_type, price_precision=2)

    assert bar.bar_type == bar_type
    assert bar.open.as_double() == 185.5
    assert bar.high.as_double() == 186.5
    assert bar.low.as_double() == 184.0
    assert bar.close.as_double() == 186.0
    assert bar.volume.as_double() == 50000.0
    # 2024-01-02 00:00:00 UTC in nanoseconds
    assert bar.ts_event == 1704153600000000000


def _trade_record(code="005930", time="093354", price="70000", volume="15", side_code="1") -> str:
    fields = ["0"] * 46
    fields[0] = code
    fields[1] = time
    fields[2] = price
    fields[12] = volume
    fields[21] = side_code
    return "^".join(fields)


def test_parse_kis_trade_message_extracts_known_fields():
    raw = f"0|H0STCNT0|001|{_trade_record()}"

    result = parse_kis_trade_message(raw)

    assert result == [
        {
            "code": "005930",
            "time": "093354",
            "price": "70000",
            "volume": "15",
            "side_code": "1",
        }
    ]


def test_parse_kis_trade_message_extracts_multiple_concatenated_records():
    raw = "0|H0STCNT0|002|" + _trade_record(price="70000") + "^" + _trade_record(
        price="70100", side_code="5"
    )

    result = parse_kis_trade_message(raw)

    assert len(result) == 2
    assert result[0]["price"] == "70000"
    assert result[0]["side_code"] == "1"
    assert result[1]["price"] == "70100"
    assert result[1]["side_code"] == "5"


def test_parse_kis_trade_message_returns_empty_list_for_non_trade_frame():
    raw = '{"header":{"tr_id":"PINGPONG"}}'

    assert parse_kis_trade_message(raw) == []


def test_parse_kis_trade_message_raises_on_wrong_field_count():
    raw = "0|H0STCNT0|001|" + "^".join(["0"] * 10)

    try:
        parse_kis_trade_message(raw)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert raw in str(exc)


def test_map_kis_trade_tick_converts_fields_to_trade_tick():
    instrument_id = InstrumentId.from_str("005930.XKRX")
    fields = {
        "code": "005930",
        "time": "093354",
        "price": "70000",
        "volume": "15",
        "side_code": "1",
    }

    tick = map_kis_trade_tick(
        fields,
        instrument_id,
        price_precision=0,
        trade_date=dt.date(2024, 6, 3),
        sequence=7,
    )

    assert tick.instrument_id == instrument_id
    assert tick.price.as_double() == 70000.0
    assert tick.size.as_double() == 15.0
    assert tick.aggressor_side == AggressorSide.BUYER
    assert str(tick.trade_id) == "005930-093354-7"
    assert tick.ts_event == 1717374834000000000  # 2024-06-03 09:33:54 KST -> UTC ns


def test_map_kis_trade_tick_maps_sell_side_code():
    instrument_id = InstrumentId.from_str("005930.XKRX")
    fields = {"code": "005930", "time": "093354", "price": "70000", "volume": "15", "side_code": "5"}

    tick = map_kis_trade_tick(fields, instrument_id, price_precision=0, trade_date=dt.date(2024, 6, 3), sequence=1)

    assert tick.aggressor_side == AggressorSide.SELLER


def test_map_kis_trade_tick_maps_unknown_side_code_to_no_aggressor():
    instrument_id = InstrumentId.from_str("005930.XKRX")
    fields = {"code": "005930", "time": "093354", "price": "70000", "volume": "15", "side_code": "9"}

    tick = map_kis_trade_tick(fields, instrument_id, price_precision=0, trade_date=dt.date(2024, 6, 3), sequence=1)

    assert tick.aggressor_side == AggressorSide.NO_AGGRESSOR


def test_build_us_equity_has_expected_fields():
    equity = build_us_equity("AAPL")

    assert equity.id == InstrumentId.from_str("AAPL.NASDAQ")
    assert str(equity.quote_currency) == "USD"
    assert equity.price_precision == 2
    assert equity.lot_size.as_double() == 1.0


def test_build_us_equity_default_venue_is_nasdaq():
    equity = build_us_equity("AAPL")

    assert equity.id == InstrumentId.from_str("AAPL.NASDAQ")


def test_build_us_equity_accepts_explicit_venue():
    equity = build_us_equity("SPY", venue="ARCA")

    assert equity.id == InstrumentId.from_str("SPY.ARCA")
    assert str(equity.quote_currency) == "USD"
    assert equity.price_precision == 2


def test_map_ib_trade_tick_converts_raw_tick_to_trade_tick():
    instrument_id = InstrumentId.from_str("AAPL.NASDAQ")
    raw_tick = SimpleNamespace(
        time=dt.datetime(2024, 6, 3, 13, 30, 0, tzinfo=dt.timezone.utc),
        price=195.50,
        size=100,
    )

    tick = map_ib_trade_tick(raw_tick, instrument_id, price_precision=2, sequence=3)

    assert tick.instrument_id == instrument_id
    assert tick.price.as_double() == 195.50
    assert tick.size.as_double() == 100.0
    assert tick.aggressor_side == AggressorSide.NO_AGGRESSOR
    assert str(tick.trade_id) == "AAPL-20240603133000-3"
    assert tick.ts_event == 1717421400000000000  # 2024-06-03 13:30:00 UTC -> ns


def test_build_kospi_index_has_expected_fields():
    index = build_kospi_index()

    assert isinstance(index, IndexInstrument)
    assert index.id == InstrumentId.from_str("KOSPI.XKRX")
    assert str(index.quote_currency) == "KRW"
    assert index.price_precision == 2


def test_map_kis_index_daily_bar_converts_row_to_bar():
    bar_type = bar_type_for(InstrumentId.from_str("KOSPI.XKRX"))
    row = {
        "stck_bsop_date": "20240102",
        "bstp_nmix_oprc": "264500",
        "bstp_nmix_hgpr": "265500",
        "bstp_nmix_lwpr": "264000",
        "bstp_nmix_prpr": "265032",
        "acml_vol": "500000000",
    }

    bar = map_kis_index_daily_bar(row, bar_type, price_precision=2)

    assert bar.bar_type == bar_type
    assert bar.open.as_double() == 2645.00
    assert bar.high.as_double() == 2655.00
    assert bar.low.as_double() == 2640.00
    assert bar.close.as_double() == 2650.32
    assert abs(bar.volume.as_double() - 500_000_000.0) < 1.0
    assert bar.ts_event == 1704153600000000000
