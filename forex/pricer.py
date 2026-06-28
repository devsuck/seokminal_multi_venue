"""Covered Interest Rate Parity (CIRP) forex pricer: forward, curve, carry."""
import math


def fx_forward(
    spot: float, r_domestic: float, r_foreign: float, T: float
) -> dict:
    """Compute FX forward rate using Covered Interest Rate Parity.

    F = spot * exp((r_domestic - r_foreign) * T)

    Args:
        spot: Current exchange rate (e.g. 1.10 for EUR/USD)
        r_domestic: Domestic (base currency) interest rate, annualised (e.g. 0.05)
        r_foreign: Foreign (quote currency) interest rate, annualised (e.g. 0.03)
        T: Time to delivery in years (T=0 returns spot)

    Returns dict with keys:
        forward, forward_points, forward_points_pct,
        annualized_differential, market_structure
    """
    diff = r_domestic - r_foreign
    if T <= 0:
        return {
            "forward": round(spot, 6),
            "forward_points": 0.0,
            "forward_points_pct": 0.0,
            "annualized_differential": round(diff * 100, 4),
            "market_structure": "flat",
        }
    F = spot * math.exp(diff * T)
    fwd_pts = F - spot
    fwd_pts_pct = (fwd_pts / spot) * 100
    if diff > 1e-9:
        structure = "premium"
    elif diff < -1e-9:
        structure = "discount"
    else:
        structure = "flat"
    return {
        "forward": round(F, 6),
        "forward_points": round(fwd_pts, 6),
        "forward_points_pct": round(fwd_pts_pct, 4),
        "annualized_differential": round(diff * 100, 4),
        "market_structure": structure,
    }


def fx_curve(
    spot: float, r_domestic: float, r_foreign: float, tenors_days: list[int]
) -> list[dict]:
    """Compute FX forward curve across multiple tenors.

    Returns list of dicts — one per tenor — each with all fx_forward keys
    plus tenor_days.
    """
    rows = []
    for days in tenors_days:
        T = days / 365.0
        fp = fx_forward(spot, r_domestic, r_foreign, T)
        rows.append({"tenor_days": days, **fp})
    return rows


def fx_carry(
    spot: float, r_domestic: float, r_foreign: float, T: float
) -> dict:
    """Carry trade analysis for an FX position.

    Buying the higher-yielding currency (r_domestic > r_foreign) earns
    carry = (r_domestic - r_foreign) per year. UIP predicts the spot
    will depreciate by the same amount, wiping out the carry gain. In
    practice, spot often moves less than UIP predicts.

    Args:
        spot: Current exchange rate
        r_domestic: Domestic interest rate (annualised)
        r_foreign: Foreign interest rate (annualised)
        T: Holding period in years

    Returns dict with keys:
        forward, carry_rate, net_carry_pct,
        breakeven_move_pct, favorable, uip_expected_move_pct
    """
    diff = r_domestic - r_foreign
    F = spot * math.exp(diff * T) if T > 0 else spot
    carry_rate = diff * 100
    net_carry_pct = diff * T * 100
    breakeven_move_pct = abs(net_carry_pct)
    uip_expected_move_pct = ((F - spot) / spot) * 100 if spot != 0 else 0.0
    return {
        "forward": round(F, 6),
        "carry_rate": round(carry_rate, 4),
        "net_carry_pct": round(net_carry_pct, 4),
        "breakeven_move_pct": round(breakeven_move_pct, 4),
        "favorable": diff > 1e-9,
        "uip_expected_move_pct": round(uip_expected_move_pct, 4),
    }
