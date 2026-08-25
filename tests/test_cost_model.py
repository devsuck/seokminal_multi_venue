from research.validation.cost_model import (
    ib_futures_effective_cost_bps,
    IB_FUTURES_COMMISSION_USD,
    IB_FUTURES_TICK_VALUE_USD,
    IB_FUTURES_SLIPPAGE_TICKS,
)


def test_ib_futures_effective_cost_bps_nq():
    # NQ: commission $2.25 + slippage(0.5 tick * $5/tick = $2.50) = $4.75 on notional 400000
    # bps = 4.75 / 400000 * 10000 = 0.11875
    result = ib_futures_effective_cost_bps("NQ", notional=400_000.0)
    assert result == round((IB_FUTURES_COMMISSION_USD["NQ"] + IB_FUTURES_SLIPPAGE_TICKS["NQ"] * IB_FUTURES_TICK_VALUE_USD["NQ"]) / 400_000.0 * 10_000.0, 6)


def test_ib_futures_effective_cost_bps_mnq_smaller_notional_higher_bps():
    nq_bps = ib_futures_effective_cost_bps("NQ", notional=400_000.0)
    mnq_bps = ib_futures_effective_cost_bps("MNQ", notional=40_000.0)
    assert mnq_bps > nq_bps  # MNQ notional 1/10인데 커미션은 1/10보다 덜 줄어듦 -> bps 더 높음


def test_ib_futures_effective_cost_bps_unknown_symbol_raises():
    import pytest
    with pytest.raises(KeyError):
        ib_futures_effective_cost_bps("ES", notional=100_000.0)
