import datetime as dt

from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import KRW
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity


def build_xkrx_equity(code: str) -> Equity:
    now_ns = dt_to_unix_nanos(dt.datetime.now(dt.timezone.utc))
    return Equity(
        instrument_id=InstrumentId.from_str(f"{code}.XKRX"),
        raw_symbol=Symbol(code),
        currency=KRW,
        price_precision=0,
        price_increment=Price.from_str("1"),
        lot_size=Quantity.from_int(1),
        ts_event=now_ns,
        ts_init=now_ns,
    )


def bar_type_for(instrument_id: InstrumentId) -> BarType:
    return BarType.from_str(f"{instrument_id}-1-DAY-LAST-EXTERNAL")


def map_kis_daily_bar(row: dict, bar_type: BarType, price_precision: int) -> Bar:
    event_date = dt.datetime.strptime(row["stck_bsop_date"], "%Y%m%d").replace(
        tzinfo=dt.timezone.utc
    )
    ts_event = dt_to_unix_nanos(event_date)

    return Bar(
        bar_type=bar_type,
        open=Price(float(row["stck_oprc"]), price_precision),
        high=Price(float(row["stck_hgpr"]), price_precision),
        low=Price(float(row["stck_lwpr"]), price_precision),
        close=Price(float(row["stck_clpr"]), price_precision),
        volume=Quantity(float(row["acml_vol"]), 0),
        ts_event=ts_event,
        ts_init=ts_event,
    )
