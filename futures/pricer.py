"""Cost-of-carry futures pricer: price, calendar term structure, roll analysis."""
import math


def futures_price(
    S: float, r: float, q: float, T: float
) -> dict:
    """Compute futures price using cost-of-carry model.

    Args:
        S: Spot price
        r: Risk-free rate (annualised, e.g. 0.05 for 5%)
        q: Convenience yield / dividend yield (annualised, e.g. 0.02 for 2%)
        T: Time to expiry in years (T=0 returns spot)

    Returns dict with keys:
        price, basis, basis_pct, annualized_carry, market_structure
    """
    carry = r - q
    if T <= 0:
        return {
            "price": round(S, 4),
            "basis": 0.0,
            "basis_pct": 0.0,
            "annualized_carry": round(carry * 100, 4),
            "market_structure": "flat",
        }
    F = S * math.exp(carry * T)
    basis = F - S
    basis_pct = (basis / S) * 100
    if carry > 1e-9:
        structure = "contango"
    elif carry < -1e-9:
        structure = "backwardation"
    else:
        structure = "flat"
    return {
        "price": round(F, 4),
        "basis": round(basis, 4),
        "basis_pct": round(basis_pct, 4),
        "annualized_carry": round(carry * 100, 4),
        "market_structure": structure,
    }


def futures_calendar(
    S: float, r: float, q: float, expiry_days: list[int]
) -> list[dict]:
    """Compute futures prices across a list of expiries (term structure).

    Returns list of dicts — one per expiry — each with all futures_price keys
    plus expiry_days.
    """
    rows = []
    for days in expiry_days:
        T = days / 365.0
        fp = futures_price(S, r, q, T)
        rows.append({"expiry_days": days, **fp})
    return rows


def futures_roll(
    S: float, r: float, q: float, front_days: int, back_days: int
) -> dict:
    """Compute rollover cost from front contract to back contract.

    Args:
        S: Spot price
        r: Risk-free rate (annualised)
        q: Convenience yield (annualised)
        front_days: Days to expiry of the nearby (front) contract
        back_days: Days to expiry of the next (back) contract; must be > front_days

    Returns dict with:
        front_days, back_days, front_price, back_price,
        roll_cost (F_back - F_front),
        roll_cost_pct (roll_cost / F_front * 100),
        annualized_roll_yield (positive = earns by rolling, negative = costs),
        days_to_roll (back_days - front_days)
    """
    T_front = front_days / 365.0
    T_back = back_days / 365.0
    carry = r - q

    F_front = S * math.exp(carry * T_front) if T_front > 0 else S
    F_back = S * math.exp(carry * T_back)

    roll_cost = F_back - F_front
    roll_cost_pct = (roll_cost / F_front) * 100 if F_front != 0 else 0.0

    days_to_roll = back_days - front_days
    if days_to_roll > 0 and F_front != 0:
        # Positive = you earn by rolling (backwardation); negative = you pay (contango)
        annualized_roll_yield = (-roll_cost / F_front) * (365.0 / days_to_roll) * 100
    else:
        annualized_roll_yield = 0.0

    return {
        "front_days": front_days,
        "back_days": back_days,
        "front_price": round(F_front, 4),
        "back_price": round(F_back, 4),
        "roll_cost": round(roll_cost, 4),
        "roll_cost_pct": round(roll_cost_pct, 4),
        "annualized_roll_yield": round(annualized_roll_yield, 4),
        "days_to_roll": days_to_roll,
    }
