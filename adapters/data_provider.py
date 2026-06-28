import datetime as dt
from zoneinfo import ZoneInfo

from ib_async.objects import BarData

from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import KRW, USD
from nautilus_trader.model.data import Bar, BarType, TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TradeId
from nautilus_trader.model.instruments import Equity, IndexInstrument
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


def build_kospi_index() -> IndexInstrument:
    now_ns = dt_to_unix_nanos(dt.datetime.now(dt.timezone.utc))
    return IndexInstrument(
        instrument_id=InstrumentId.from_str("KOSPI.XKRX"),
        raw_symbol=Symbol("0001"),
        currency=KRW,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        size_precision=0,
        size_increment=Quantity.from_int(1),
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


def map_kis_index_daily_bar(row: dict, bar_type: BarType, price_precision: int) -> Bar:
    event_date = dt.datetime.strptime(row["stck_bsop_date"], "%Y%m%d").replace(
        tzinfo=dt.timezone.utc
    )
    ts_event = dt_to_unix_nanos(event_date)

    return Bar(
        bar_type=bar_type,
        open=Price(float(row["bstp_nmix_oprc"]), price_precision),
        high=Price(float(row["bstp_nmix_hgpr"]), price_precision),
        low=Price(float(row["bstp_nmix_lwpr"]), price_precision),
        close=Price(float(row["bstp_nmix_prpr"]), price_precision),
        volume=Quantity(float(row["acml_vol"]), 0),
        ts_event=ts_event,
        ts_init=ts_event,
    )


TRADE_TR_ID = "H0STCNT0"
TRADE_FIELD_COUNT = 46
TRADE_CODE_IDX = 0
TRADE_TIME_IDX = 1
TRADE_PRICE_IDX = 2
TRADE_VOLUME_IDX = 12
TRADE_SIDE_IDX = 21

SIDE_CODE_BUY = "1"
SIDE_CODE_SELL = "5"

KST = ZoneInfo("Asia/Seoul")


def parse_kis_trade_message(raw: str) -> list[dict]:
    parts = raw.split("|")
    if len(parts) < 4 or parts[1] != TRADE_TR_ID:
        return []

    record_count = int(parts[2])
    fields = parts[3].split("^")
    expected_field_count = TRADE_FIELD_COUNT * record_count
    if len(fields) != expected_field_count:
        raise ValueError(
            f"expected {expected_field_count} fields in KIS trade frame "
            f"({record_count} records), got {len(fields)}: {raw!r}"
        )

    records = []
    for i in range(record_count):
        record = fields[i * TRADE_FIELD_COUNT : (i + 1) * TRADE_FIELD_COUNT]
        records.append(
            {
                "code": record[TRADE_CODE_IDX],
                "time": record[TRADE_TIME_IDX],
                "price": record[TRADE_PRICE_IDX],
                "volume": record[TRADE_VOLUME_IDX],
                "side_code": record[TRADE_SIDE_IDX],
            }
        )
    return records


def map_kis_trade_tick(
    fields: dict,
    instrument_id: InstrumentId,
    price_precision: int,
    trade_date: dt.date,
    sequence: int,
) -> TradeTick:
    side_code = fields["side_code"]
    if side_code == SIDE_CODE_BUY:
        aggressor_side = AggressorSide.BUYER
    elif side_code == SIDE_CODE_SELL:
        aggressor_side = AggressorSide.SELLER
    else:
        aggressor_side = AggressorSide.NO_AGGRESSOR

    time_str = fields["time"]
    event_dt = dt.datetime.combine(
        trade_date,
        dt.time(int(time_str[0:2]), int(time_str[2:4]), int(time_str[4:6])),
        tzinfo=KST,
    )
    ts_event = dt_to_unix_nanos(event_dt)

    return TradeTick(
        instrument_id=instrument_id,
        price=Price(float(fields["price"]), price_precision),
        size=Quantity(float(fields["volume"]), 0),
        aggressor_side=aggressor_side,
        trade_id=TradeId(f"{fields['code']}-{fields['time']}-{sequence}"),
        ts_event=ts_event,
        ts_init=ts_event,
    )


def build_us_equity(symbol: str, venue: str = "NASDAQ") -> Equity:
    now_ns = dt_to_unix_nanos(dt.datetime.now(dt.timezone.utc))
    return Equity(
        instrument_id=InstrumentId.from_str(f"{symbol}.{venue}"),
        raw_symbol=Symbol(symbol),
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=now_ns,
        ts_init=now_ns,
    )


def map_ib_trade_tick(
    raw_tick,
    instrument_id: InstrumentId,
    price_precision: int,
    sequence: int,
) -> TradeTick:
    ts_event = dt_to_unix_nanos(raw_tick.time)
    time_str = raw_tick.time.strftime("%Y%m%d%H%M%S")

    return TradeTick(
        instrument_id=instrument_id,
        price=Price(float(raw_tick.price), price_precision),
        size=Quantity(float(raw_tick.size), 0),
        aggressor_side=AggressorSide.NO_AGGRESSOR,
        trade_id=TradeId(f"{instrument_id.symbol}-{time_str}-{sequence}"),
        ts_event=ts_event,
        ts_init=ts_event,
    )


def build_kosdaq_equity(code: str) -> Equity:
    now_ns = dt_to_unix_nanos(dt.datetime.now(dt.timezone.utc))
    return Equity(
        instrument_id=InstrumentId.from_str(f"{code}.XKOS"),
        raw_symbol=Symbol(code),
        currency=KRW,
        price_precision=0,
        price_increment=Price.from_str("1"),
        lot_size=Quantity.from_int(1),
        ts_event=now_ns,
        ts_init=now_ns,
    )


def map_ib_daily_bar(row: BarData, bar_type: BarType, price_precision: int) -> Bar:
    event_date = dt.datetime.combine(row.date, dt.time.min, tzinfo=dt.timezone.utc)
    ts_event = dt_to_unix_nanos(event_date)

    return Bar(
        bar_type=bar_type,
        open=Price(float(row.open), price_precision),
        high=Price(float(row.high), price_precision),
        low=Price(float(row.low), price_precision),
        close=Price(float(row.close), price_precision),
        volume=Quantity(float(row.volume), 0),
        ts_event=ts_event,
        ts_init=ts_event,
    )
