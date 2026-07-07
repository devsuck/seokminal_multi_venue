"""realized_vol / vrp_spread 테스트."""
from options.pricer import realized_vol, vrp_spread


def test_realized_vol_insufficient_data_returns_none():
    assert realized_vol([100.0] * 5, window=20) is None


def test_realized_vol_zero_for_flat_prices():
    closes = [100.0] * 25
    rv = realized_vol(closes, window=20)
    assert rv == 0.0


def test_realized_vol_positive_for_noisy_prices():
    closes = [100.0, 102.0, 98.0, 103.0, 97.0] * 6
    rv = realized_vol(closes, window=20)
    assert rv is not None
    assert rv > 0.0


def test_vrp_spread_positive_when_iv_richer_than_rv():
    closes = [100.0, 102.0, 98.0, 103.0, 97.0] * 6
    result = vrp_spread(atm_iv=0.80, closes=closes, window=20)
    assert result is not None
    assert result["realized_vol"] > 0.0
    assert result["spread"] == result["atm_iv"] - result["realized_vol"]
    assert result["spread"] > 0
    assert result["spread_pct"] == result["spread"] / result["realized_vol"]


def test_vrp_spread_none_when_rv_is_zero():
    assert vrp_spread(atm_iv=0.20, closes=[100.0] * 25, window=20) is None


def test_vrp_spread_none_when_rv_unavailable():
    assert vrp_spread(atm_iv=0.20, closes=[100.0] * 3, window=20) is None
