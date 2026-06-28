"""Tests for Black-Scholes option pricer."""
import math
import pytest

from options.pricer import bs_price, bs_greeks, implied_vol, bs_chain, bs_iv_surface


# ── bs_price ──────────────────────────────────────────────────────────────────

def test_bs_price_call_atm():
    """ATM call should be positive and less than spot."""
    price = bs_price(S=100, K=100, T=1.0, r=0.05, sigma=0.2, option_type="call")
    assert 0 < price < 100


def test_bs_price_put_atm():
    """ATM put should be positive and less than strike."""
    price = bs_price(S=100, K=100, T=1.0, r=0.05, sigma=0.2, option_type="put")
    assert 0 < price < 100


def test_bs_price_put_call_parity():
    """C - P = S - K*e^(-rT) (put-call parity)."""
    S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.2
    C = bs_price(S, K, T, r, sigma, "call")
    P = bs_price(S, K, T, r, sigma, "put")
    expected = S - K * math.exp(-r * T)
    assert abs((C - P) - expected) < 1e-8


def test_bs_price_deep_itm_call():
    """Deep ITM call price ≈ S - K*e^(-rT)."""
    S, K, T, r, sigma = 200.0, 100.0, 1.0, 0.05, 0.2
    price = bs_price(S, K, T, r, sigma, "call")
    lower_bound = S - K * math.exp(-r * T)
    assert price > lower_bound * 0.99


def test_bs_price_zero_expiry_call():
    """At expiry, call = max(S-K, 0)."""
    assert bs_price(110, 100, 0, 0.05, 0.2, "call") == pytest.approx(10.0, abs=1e-8)
    assert bs_price(90, 100, 0, 0.05, 0.2, "call") == pytest.approx(0.0, abs=1e-8)


def test_bs_price_zero_expiry_put():
    """At expiry, put = max(K-S, 0)."""
    assert bs_price(90, 100, 0, 0.05, 0.2, "put") == pytest.approx(10.0, abs=1e-8)
    assert bs_price(110, 100, 0, 0.05, 0.2, "put") == pytest.approx(0.0, abs=1e-8)


# ── bs_greeks ─────────────────────────────────────────────────────────────────

def test_greeks_call_delta_bounds():
    """Call delta ∈ (0, 1)."""
    g = bs_greeks(100, 100, 1.0, 0.05, 0.2, "call")
    assert 0 < g["delta"] < 1


def test_greeks_put_delta_bounds():
    """Put delta ∈ (-1, 0)."""
    g = bs_greeks(100, 100, 1.0, 0.05, 0.2, "put")
    assert -1 < g["delta"] < 0


def test_greeks_gamma_positive():
    """Gamma > 0 for both call and put."""
    for ot in ("call", "put"):
        g = bs_greeks(100, 100, 1.0, 0.05, 0.2, ot)
        assert g["gamma"] > 0


def test_greeks_vega_positive():
    """Vega > 0 for both call and put."""
    for ot in ("call", "put"):
        g = bs_greeks(100, 100, 1.0, 0.05, 0.2, ot)
        assert g["vega"] > 0


def test_greeks_call_theta_negative():
    """Call theta < 0 (time decay hurts long options)."""
    g = bs_greeks(100, 100, 1.0, 0.05, 0.2, "call")
    assert g["theta"] < 0


def test_greeks_call_delta_atm():
    """ATM call delta ≈ 0.5–0.6 (between 0.5 and 0.7 for realistic params)."""
    g = bs_greeks(100, 100, 1.0, 0.05, 0.2, "call")
    assert 0.5 < g["delta"] < 0.7


def test_greeks_call_put_delta_sum():
    """Call delta + |put delta| ≈ 1 (from put-call parity derivative)."""
    S, K, T, r, sigma = 100, 100, 1.0, 0.05, 0.2
    call_g = bs_greeks(S, K, T, r, sigma, "call")
    put_g = bs_greeks(S, K, T, r, sigma, "put")
    assert abs(call_g["delta"] + abs(put_g["delta"]) - 1.0) < 0.001


# ── implied_vol ───────────────────────────────────────────────────────────────

def test_implied_vol_round_trip():
    """IV inversion: bs_price(sigma) → implied_vol → original sigma."""
    S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.25
    price = bs_price(S, K, T, r, sigma, "call")
    iv = implied_vol(price, S, K, T, r, "call")
    assert iv is not None
    assert abs(iv - sigma) < 1e-4


def test_implied_vol_intrinsic_returns_none():
    """Market price below intrinsic value returns None."""
    iv = implied_vol(0.01, 200, 100, 1.0, 0.05, "call")  # deep ITM call, intrinsic=100, price 0.01 << intrinsic
    assert iv is None


def test_implied_vol_zero_expiry_returns_none():
    """Zero time to expiry returns None."""
    iv = implied_vol(10.0, 110, 100, 0, 0.05, "call")
    assert iv is None


# ── bs_chain ──────────────────────────────────────────────────────────────────

def test_bs_chain_structure():
    """Chain returns list of dicts with required keys."""
    strikes = [90.0, 95.0, 100.0, 105.0, 110.0]
    chain = bs_chain(S=100, expiry_days=30, r=0.05, sigma=0.2, strikes=strikes)
    assert len(chain) == 5
    required = {"strike", "call_price", "call_delta", "call_gamma", "call_theta",
                "call_vega", "put_price", "put_delta", "put_gamma", "put_theta", "put_vega"}
    for row in chain:
        assert required <= set(row.keys())


def test_bs_chain_atm_call_above_put():
    """ATM call price > ATM put when r > 0."""
    chain = bs_chain(100, 252, 0.05, 0.2, [100.0])
    row = chain[0]
    assert row["call_price"] > row["put_price"]


def test_bs_chain_itm_otm_ordering():
    """ITM call (S>K) is more expensive than OTM call (S<K)."""
    chain = bs_chain(100, 30, 0.05, 0.2, [90.0, 110.0])
    itm = next(r for r in chain if r["strike"] == 90.0)
    otm = next(r for r in chain if r["strike"] == 110.0)
    assert itm["call_price"] > otm["call_price"]


# ── bs_iv_surface ─────────────────────────────────────────────────────────────

def test_bs_iv_surface_shape():
    """Surface returns correctly shaped grid."""
    result = bs_iv_surface(S=100, r=0.05, atm_vol=0.2)
    assert "strikes" in result
    assert "expiry_days" in result
    assert "iv_surface" in result
    assert len(result["iv_surface"]) == len(result["strikes"])
    assert len(result["iv_surface"][0]) == len(result["expiry_days"])


def test_bs_iv_surface_positive_ivs():
    """All IV values must be positive."""
    result = bs_iv_surface(S=100, r=0.05, atm_vol=0.2)
    for row in result["iv_surface"]:
        for val in row:
            assert val > 0
