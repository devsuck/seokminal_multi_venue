import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from correlation_analysis.returns import compute_returns

BAR_TYPE = "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL"


def _bar(price: float, ts: int) -> Bar:
    return Bar(
        bar_type=BarType.from_str(BAR_TYPE),
        open=Price.from_str(f"{price:.2f}"),
        high=Price.from_str(f"{price + 1:.2f}"),
        low=Price.from_str(f"{price - 1:.2f}"),
        close=Price.from_str(f"{price:.2f}"),
        volume=Quantity.from_str("10"),
        ts_event=ts,
        ts_init=ts,
    )


def test_compute_returns_skips_first_bar():
    bars = [_bar(100.0, 0)]

    returns = compute_returns(bars)

    assert returns == {}


def test_compute_returns_computes_pct_change_keyed_by_ts_event():
    bars = [_bar(100.0, 0), _bar(110.0, 1), _bar(99.0, 2)]

    returns = compute_returns(bars)

    assert returns == {
        1: pytest.approx(0.1),
        2: pytest.approx(99.0 / 110.0 - 1.0),
    }


def test_compute_returns_on_empty_list():
    assert compute_returns([]) == {}
