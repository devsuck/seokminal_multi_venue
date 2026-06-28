"""Tests for Covered Interest Rate Parity (CIRP) forex pricer."""
import math
import pytest

from forex.pricer import fx_forward, fx_curve, fx_carry


# ── fx_forward ────────────────────────────────────────────────────────────────

def test_fx_forward_premium():
    """When r_domestic > r_foreign, forward > spot → 'premium'."""
    result = fx_forward(1.10, r_domestic=0.05, r_foreign=0.03, T=1.0)
    assert result["forward"] > 1.10
    assert result["market_structure"] == "premium"


def test_fx_forward_discount():
    """When r_domestic < r_foreign, forward < spot → 'discount'."""
    result = fx_forward(1.10, r_domestic=0.02, r_foreign=0.06, T=1.0)
    assert result["forward"] < 1.10
    assert result["market_structure"] == "discount"


def test_fx_forward_flat():
    """When r_domestic == r_foreign, forward == spot → 'flat'."""
    result = fx_forward(1.10, r_domestic=0.04, r_foreign=0.04, T=1.0)
    assert result["forward"] == pytest.approx(1.10, abs=1e-6)
    assert result["market_structure"] == "flat"


def test_fx_forward_formula():
    """F = S * exp((r_d - r_f) * T) exactly."""
    S, r_d, r_f, T = 1.25, 0.06, 0.02, 0.5
    result = fx_forward(S, r_d, r_f, T)
    expected = S * math.exp((r_d - r_f) * T)
    assert result["forward"] == pytest.approx(expected, abs=1e-5)


def test_fx_forward_points():
    """forward_points = forward - spot."""
    result = fx_forward(1.10, 0.05, 0.03, 1.0)
    assert result["forward_points"] == pytest.approx(result["forward"] - 1.10, abs=1e-6)


def test_fx_forward_points_pct():
    """forward_points_pct = (forward - spot) / spot * 100."""
    result = fx_forward(1.10, 0.05, 0.03, 1.0)
    expected_pct = (result["forward"] - 1.10) / 1.10 * 100
    assert result["forward_points_pct"] == pytest.approx(expected_pct, abs=1e-4)


def test_fx_forward_annualized_differential():
    """annualized_differential = (r_domestic - r_foreign) * 100."""
    result = fx_forward(1.10, 0.05, 0.03, 1.0)
    assert result["annualized_differential"] == pytest.approx(2.0, abs=1e-6)


def test_fx_forward_zero_T():
    """At T=0, forward == spot, forward_points == 0."""
    result = fx_forward(1.30, 0.05, 0.03, T=0)
    assert result["forward"] == pytest.approx(1.30, abs=1e-6)
    assert result["forward_points"] == pytest.approx(0.0, abs=1e-6)
    assert result["market_structure"] == "flat"


def test_fx_forward_required_keys():
    """Result has all required keys."""
    result = fx_forward(1.10, 0.05, 0.03, 1.0)
    required = {"forward", "forward_points", "forward_points_pct", "annualized_differential", "market_structure"}
    assert required <= set(result.keys())


# ── fx_curve ──────────────────────────────────────────────────────────────────

def test_fx_curve_structure():
    """fx_curve returns one dict per tenor with required keys."""
    rows = fx_curve(1.10, 0.05, 0.03, [7, 30, 60, 90, 180, 365])
    assert len(rows) == 6
    required = {"tenor_days", "forward", "forward_points", "forward_points_pct",
                "annualized_differential", "market_structure"}
    for row in rows:
        assert required <= set(row.keys())


def test_fx_curve_tenor_days():
    """Each row carries the correct tenor_days value."""
    tenors = [7, 30, 60, 90, 180, 365]
    rows = fx_curve(1.10, 0.05, 0.03, tenors)
    assert [r["tenor_days"] for r in rows] == tenors


def test_fx_curve_monotone_premium():
    """In premium (r_d > r_f), forward increases with tenor."""
    rows = fx_curve(1.10, 0.05, 0.01, [7, 30, 90, 180, 365])
    prices = [r["forward"] for r in rows]
    assert prices == sorted(prices)


def test_fx_curve_monotone_discount():
    """In discount (r_d < r_f), forward decreases with tenor."""
    rows = fx_curve(1.10, 0.01, 0.07, [7, 30, 90, 180, 365])
    prices = [r["forward"] for r in rows]
    assert prices == sorted(prices, reverse=True)


# ── fx_carry ──────────────────────────────────────────────────────────────────

def test_fx_carry_required_keys():
    """Result has all required keys."""
    result = fx_carry(1.10, 0.05, 0.03, 1.0)
    required = {"forward", "carry_rate", "net_carry_pct", "breakeven_move_pct",
                "favorable", "uip_expected_move_pct"}
    assert required <= set(result.keys())


def test_fx_carry_favorable_when_premium():
    """favorable == True when r_domestic > r_foreign."""
    result = fx_carry(1.10, 0.05, 0.03, 1.0)
    assert result["favorable"] is True


def test_fx_carry_unfavorable_when_discount():
    """favorable == False when r_domestic < r_foreign."""
    result = fx_carry(1.10, 0.02, 0.06, 1.0)
    assert result["favorable"] is False


def test_fx_carry_rate_formula():
    """carry_rate = (r_domestic - r_foreign) * 100."""
    result = fx_carry(1.10, 0.05, 0.03, 1.0)
    assert result["carry_rate"] == pytest.approx(2.0, abs=1e-6)


def test_fx_carry_forward_matches_cirp():
    """forward matches F = S * exp((r_d - r_f) * T)."""
    S, r_d, r_f, T = 1.25, 0.06, 0.02, 0.75
    result = fx_carry(S, r_d, r_f, T)
    expected = S * math.exp((r_d - r_f) * T)
    assert result["forward"] == pytest.approx(expected, abs=1e-5)


def test_fx_carry_breakeven_is_nonnegative():
    """breakeven_move_pct is always >= 0."""
    assert fx_carry(1.10, 0.05, 0.03, 1.0)["breakeven_move_pct"] >= 0
    assert fx_carry(1.10, 0.02, 0.06, 1.0)["breakeven_move_pct"] >= 0
