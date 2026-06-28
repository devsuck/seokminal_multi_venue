"""Tests for cost-of-carry futures pricer."""
import math
import pytest

from futures.pricer import futures_price, futures_calendar, futures_roll


# ── futures_price ─────────────────────────────────────────────────────────────

def test_futures_price_contango():
    """When r > q, futures price > spot (contango)."""
    result = futures_price(S=100, r=0.05, q=0.02, T=1.0)
    assert result["price"] > 100
    assert result["market_structure"] == "contango"


def test_futures_price_backwardation():
    """When q > r, futures price < spot (backwardation)."""
    result = futures_price(S=100, r=0.02, q=0.06, T=1.0)
    assert result["price"] < 100
    assert result["market_structure"] == "backwardation"


def test_futures_price_flat():
    """When r == q, futures price == spot (flat)."""
    result = futures_price(S=100, r=0.04, q=0.04, T=1.0)
    assert result["price"] == pytest.approx(100.0, abs=1e-6)
    assert result["market_structure"] == "flat"


def test_futures_price_formula():
    """F = S * exp((r - q) * T) exactly."""
    S, r, q, T = 150.0, 0.06, 0.01, 0.5
    result = futures_price(S, r, q, T)
    expected = S * math.exp((r - q) * T)
    assert result["price"] == pytest.approx(expected, abs=1e-4)


def test_futures_price_basis():
    """basis = F - S."""
    result = futures_price(S=100, r=0.05, q=0.02, T=1.0)
    assert result["basis"] == pytest.approx(result["price"] - 100.0, abs=1e-6)


def test_futures_price_basis_pct():
    """basis_pct = (F - S) / S * 100."""
    result = futures_price(S=100, r=0.05, q=0.02, T=1.0)
    expected_pct = (result["price"] - 100.0) / 100.0 * 100.0
    assert result["basis_pct"] == pytest.approx(expected_pct, abs=1e-4)


def test_futures_price_annualized_carry():
    """annualized_carry = (r - q) * 100."""
    result = futures_price(S=100, r=0.05, q=0.02, T=1.0)
    assert result["annualized_carry"] == pytest.approx(3.0, abs=1e-6)


def test_futures_price_zero_expiry():
    """At T=0, futures price equals spot, basis=0."""
    result = futures_price(S=100, r=0.05, q=0.02, T=0)
    assert result["price"] == pytest.approx(100.0, abs=1e-6)
    assert result["basis"] == pytest.approx(0.0, abs=1e-6)
    assert result["market_structure"] == "flat"


def test_futures_price_required_keys():
    """Result has all required keys."""
    result = futures_price(100, 0.05, 0.02, 1.0)
    required = {"price", "basis", "basis_pct", "annualized_carry", "market_structure"}
    assert required <= set(result.keys())


# ── futures_calendar ──────────────────────────────────────────────────────────

def test_futures_calendar_structure():
    """Calendar returns list of dicts with required keys."""
    rows = futures_calendar(S=100, r=0.05, q=0.02, expiry_days=[30, 60, 90])
    assert len(rows) == 3
    required = {"expiry_days", "price", "basis", "basis_pct", "annualized_carry", "market_structure"}
    for row in rows:
        assert required <= set(row.keys())


def test_futures_calendar_expiry_days():
    """Each row carries the correct expiry_days."""
    rows = futures_calendar(100, 0.05, 0.02, [30, 60, 90])
    assert [r["expiry_days"] for r in rows] == [30, 60, 90]


def test_futures_calendar_monotone_contango():
    """In contango (r > q), later expiries have higher prices."""
    rows = futures_calendar(100, 0.05, 0.01, [30, 60, 90, 180])
    prices = [r["price"] for r in rows]
    assert prices == sorted(prices)


def test_futures_calendar_monotone_backwardation():
    """In backwardation (q > r), later expiries have lower prices."""
    rows = futures_calendar(100, 0.01, 0.07, [30, 60, 90, 180])
    prices = [r["price"] for r in rows]
    assert prices == sorted(prices, reverse=True)


# ── futures_roll ──────────────────────────────────────────────────────────────

def test_futures_roll_structure():
    """Roll result has all required keys."""
    result = futures_roll(100, 0.05, 0.02, front_days=30, back_days=60)
    required = {
        "front_days", "back_days", "front_price", "back_price",
        "roll_cost", "roll_cost_pct", "annualized_roll_yield", "days_to_roll"
    }
    assert required <= set(result.keys())


def test_futures_roll_days_to_roll():
    """days_to_roll = back_days - front_days."""
    result = futures_roll(100, 0.05, 0.02, front_days=30, back_days=90)
    assert result["days_to_roll"] == 60


def test_futures_roll_contango_positive_cost():
    """Contango: rolling forward costs money (roll_cost > 0)."""
    result = futures_roll(100, 0.05, 0.01, front_days=30, back_days=60)
    assert result["roll_cost"] > 0


def test_futures_roll_backwardation_negative_cost():
    """Backwardation: rolling forward earns money (roll_cost < 0)."""
    result = futures_roll(100, 0.01, 0.07, front_days=30, back_days=60)
    assert result["roll_cost"] < 0


def test_futures_roll_yield_sign():
    """In contango, annualized_roll_yield < 0 (cost to roll)."""
    result = futures_roll(100, 0.05, 0.01, front_days=30, back_days=60)
    assert result["annualized_roll_yield"] < 0


def test_futures_roll_price_formula():
    """front_price and back_price match futures_price formula."""
    S, r, q = 100.0, 0.05, 0.02
    result = futures_roll(S, r, q, 30, 60)
    expected_front = S * math.exp((r - q) * 30 / 365.0)
    expected_back = S * math.exp((r - q) * 60 / 365.0)
    assert result["front_price"] == pytest.approx(expected_front, abs=1e-4)
    assert result["back_price"] == pytest.approx(expected_back, abs=1e-4)
