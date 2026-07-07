"""Black-Scholes option pricer: price, Greeks, IV, chain, IV surface."""
import math
import numpy as np
from scipy.stats import norm


def bs_price(
    S: float, K: float, T: float, r: float, sigma: float, option_type: str
) -> float:
    """Black-Scholes option price.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry in years (T=0 returns intrinsic value)
        r: Risk-free rate (annualised, e.g. 0.05 for 5%)
        sigma: Implied volatility (annualised, e.g. 0.2 for 20%)
        option_type: "call" or "put"
    """
    if T <= 0:
        return max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_greeks(
    S: float, K: float, T: float, r: float, sigma: float, option_type: str
) -> dict:
    """Compute option Greeks.

    Returns dict with keys: delta, gamma, theta, vega, rho.
    - theta is per calendar day (divided by 365)
    - vega is per 1 percentage-point change in vol (divided by 100)
    - rho is per 1 percentage-point change in rate (divided by 100)
    """
    if T <= 0:
        delta = 1.0 if (option_type == "call" and S > K) else (
            -1.0 if (option_type == "put" and S < K) else 0.0
        )
        return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    pdf_d1 = norm.pdf(d1)

    gamma = pdf_d1 / (S * sigma * sqrt_T)
    vega = S * pdf_d1 * sqrt_T / 100.0

    if option_type == "call":
        delta = norm.cdf(d1)
        theta = (
            -S * pdf_d1 * sigma / (2.0 * sqrt_T)
            - r * K * math.exp(-r * T) * norm.cdf(d2)
        ) / 365.0
        rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100.0
    else:
        delta = norm.cdf(d1) - 1.0
        theta = (
            -S * pdf_d1 * sigma / (2.0 * sqrt_T)
            + r * K * math.exp(-r * T) * norm.cdf(-d2)
        ) / 365.0
        rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100.0

    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega, "rho": rho}


def implied_vol(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float | None:
    """Compute implied volatility via Newton-Raphson.

    Returns None if no solution exists (e.g. T=0 or price <= intrinsic).
    """
    if T <= 0:
        return None
    intrinsic = max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
    if market_price <= intrinsic + 1e-10:
        return None

    sigma = 0.3
    for _ in range(max_iter):
        price = bs_price(S, K, T, r, sigma, option_type)
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        vega_raw = S * norm.pdf(d1) * sqrt_T
        if abs(vega_raw) < 1e-10:
            return None
        sigma -= (price - market_price) / vega_raw
        if sigma <= 0:
            return None
        if abs(bs_price(S, K, T, r, sigma, option_type) - market_price) < tol:
            break
    return sigma


def bs_chain(
    S: float,
    expiry_days: int,
    r: float,
    sigma: float,
    strikes: list[float],
) -> list[dict]:
    """Compute option chain for a list of strikes.

    Returns list of dicts, one per strike, with call+put price and Greeks.
    """
    T = expiry_days / 365.0
    rows = []
    for K in strikes:
        call_greeks = bs_greeks(S, K, T, r, sigma, "call")
        put_greeks = bs_greeks(S, K, T, r, sigma, "put")
        rows.append({
            "strike": K,
            "call_price": round(bs_price(S, K, T, r, sigma, "call"), 4),
            "call_delta": round(call_greeks["delta"], 4),
            "call_gamma": round(call_greeks["gamma"], 6),
            "call_theta": round(call_greeks["theta"], 4),
            "call_vega": round(call_greeks["vega"], 4),
            "put_price": round(bs_price(S, K, T, r, sigma, "put"), 4),
            "put_delta": round(put_greeks["delta"], 4),
            "put_gamma": round(put_greeks["gamma"], 6),
            "put_theta": round(put_greeks["theta"], 4),
            "put_vega": round(put_greeks["vega"], 4),
        })
    return rows


def realized_vol(closes: list[float], window: int = 20) -> float | None:
    """Close-to-close annualised realized volatility over the trailing window.

    Args:
        closes: daily close prices, oldest first
        window: number of trailing log-returns to use

    Returns None if insufficient data (< window+1 closes).
    """
    if len(closes) < window + 1:
        return None
    tail = closes[-(window + 1):]
    log_rets = [math.log(tail[i] / tail[i - 1]) for i in range(1, len(tail)) if tail[i - 1] > 0]
    if len(log_rets) < 2:
        return None
    mean = sum(log_rets) / len(log_rets)
    var = sum((x - mean) ** 2 for x in log_rets) / (len(log_rets) - 1)
    return math.sqrt(var) * math.sqrt(252)


def vrp_spread(atm_iv: float, closes: list[float], window: int = 20) -> dict | None:
    """Variance risk premium: how much richer implied vol is vs realized vol.

    Returns {"atm_iv", "realized_vol", "spread", "spread_pct"} or None if RV
    unavailable. spread_pct is spread / realized_vol (relative richness).
    """
    rv = realized_vol(closes, window)
    if rv is None or rv <= 0:
        return None
    spread = atm_iv - rv
    return {
        "atm_iv": atm_iv,
        "realized_vol": rv,
        "spread": spread,
        "spread_pct": spread / rv,
    }


def bs_iv_surface(
    S: float,
    r: float,
    atm_vol: float,
    skew: float = 0.1,
    smile: float = 0.3,
) -> dict:
    """Compute a synthetic IV surface using a parametric vol model.

    Model: sigma(K, T) = atm_vol * (1 - skew*m + smile*m^2) * term_factor
    where m = ln(K/F) / (atm_vol * sqrt(T)) — normalised log-moneyness
    and term_factor = 1 + 0.08 * (1 - sqrt(T))  — upward term slope for short expiries

    Returns:
        {
            "strikes": [float],         # 9 strikes from 0.8*S to 1.2*S
            "expiry_days": [int],       # 7 expiries: 30,60,90,120,180,252,360
            "iv_surface": [[float]],    # [n_strikes][n_expiries], IV as fraction
        }
    """
    expiry_days = [30, 60, 90, 120, 180, 252, 360]
    # 9 strikes evenly spaced from 80% to 120% of spot
    moneyness_levels = np.linspace(0.80, 1.20, 9)
    strikes = [round(S * m, 2) for m in moneyness_levels]

    iv_surface = []
    for K in strikes:
        row = []
        for days in expiry_days:
            T = days / 365.0
            F = S * math.exp(r * T)
            sqrt_T = math.sqrt(T)
            # Normalised log-moneyness
            m = math.log(K / F) / (atm_vol * sqrt_T) if atm_vol * sqrt_T > 0 else 0.0
            term_factor = 1.0 + 0.08 * (1.0 - sqrt_T)
            iv = atm_vol * (1.0 - skew * m + smile * m**2) * term_factor
            row.append(round(max(0.01, iv), 4))
        iv_surface.append(row)

    return {
        "strikes": strikes,
        "expiry_days": expiry_days,
        "iv_surface": iv_surface,
    }
