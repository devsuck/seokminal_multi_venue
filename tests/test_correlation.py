import tempfile

import pytest
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from correlation_analysis.correlation import corr_matrix


def _equity(symbol: str) -> Equity:
    return Equity(
        instrument_id=InstrumentId.from_str(f"{symbol}.NASDAQ"),
        raw_symbol=Symbol(symbol),
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def _bar_type_str(symbol: str) -> str:
    return f"{symbol}.NASDAQ-1-DAY-LAST-EXTERNAL"


def _bar(symbol: str, price: float, ts: int) -> Bar:
    return Bar(
        bar_type=BarType.from_str(_bar_type_str(symbol)),
        open=Price.from_str(f"{price:.2f}"),
        high=Price.from_str(f"{price + 1:.2f}"),
        low=Price.from_str(f"{price - 1:.2f}"),
        close=Price.from_str(f"{price:.2f}"),
        volume=Quantity.from_str("10"),
        ts_event=ts,
        ts_init=ts,
    )


def test_corr_matrix_identifies_perfect_positive_and_negative_correlation():
    # AAA tracks a rising price path; BBB is the exact inverse; CCC is unrelated.
    aaa_prices = [100, 102, 101, 105, 103, 108]
    bbb_prices = [100, 98, 99, 95, 97, 92]
    ccc_prices = [50, 51.56, 53.33, 53.29, 51.32, 50.5]

    aaa_bars = [_bar("AAA", p, i * 86_400_000_000_000) for i, p in enumerate(aaa_prices)]
    bbb_bars = [_bar("BBB", p, i * 86_400_000_000_000) for i, p in enumerate(bbb_prices)]
    ccc_bars = [_bar("CCC", p, i * 86_400_000_000_000) for i, p in enumerate(ccc_prices)]

    with tempfile.TemporaryDirectory() as tmp_dir:
        catalog = ParquetDataCatalog(tmp_dir)
        catalog.write_data([_equity("AAA"), _equity("BBB"), _equity("CCC")])
        catalog.write_data(aaa_bars + bbb_bars + ccc_bars)

        result = corr_matrix(
            instrument_ids=["AAA.NASDAQ", "BBB.NASDAQ", "CCC.NASDAQ"],
            bar_type_strs=[_bar_type_str("AAA"), _bar_type_str("BBB"), _bar_type_str("CCC")],
            start_ns=0,
            end_ns=aaa_bars[-1].ts_event,
            catalog_path=tmp_dir,
        )

    assert result[("AAA.NASDAQ", "AAA.NASDAQ")] == pytest.approx(1.0)
    assert result[("AAA.NASDAQ", "BBB.NASDAQ")] == pytest.approx(-1.0, abs=0.05)
    assert result[("BBB.NASDAQ", "AAA.NASDAQ")] == pytest.approx(-1.0, abs=0.05)
    assert -0.9 < result[("AAA.NASDAQ", "CCC.NASDAQ")] < 0.9


def test_corr_matrix_rejects_fewer_than_two_instruments():
    with pytest.raises(ValueError, match="at least 2"):
        corr_matrix(
            instrument_ids=["AAA.NASDAQ"],
            bar_type_strs=[_bar_type_str("AAA")],
            start_ns=0,
            end_ns=1,
            catalog_path="./irrelevant",
        )


def test_corr_matrix_raises_on_no_common_dates():
    aaa_bars = [_bar("AAA", 100 + i, i * 86_400_000_000_000) for i in range(5)]
    bbb_bars = [_bar("BBB", 100 + i, (i + 100) * 86_400_000_000_000) for i in range(5)]

    with tempfile.TemporaryDirectory() as tmp_dir:
        catalog = ParquetDataCatalog(tmp_dir)
        catalog.write_data([_equity("AAA"), _equity("BBB")])
        catalog.write_data(aaa_bars + bbb_bars)

        with pytest.raises(ValueError, match="common"):
            corr_matrix(
                instrument_ids=["AAA.NASDAQ", "BBB.NASDAQ"],
                bar_type_strs=[_bar_type_str("AAA"), _bar_type_str("BBB")],
                start_ns=0,
                end_ns=200 * 86_400_000_000_000,
                catalog_path=tmp_dir,
            )
