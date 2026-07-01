"""Pairs trading: Johansen cointegration test + spread analysis."""
import numpy as np
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from statsmodels.tsa.stattools import coint, adfuller


def test_cointegration(prices_a: list[float], prices_b: list[float]) -> dict:
    """Engle-Granger cointegration test."""
    pa = np.array(prices_a)
    pb = np.array(prices_b)

    # Engle-Granger test
    t_stat, p_val, crit_vals = coint(pa, pb)
    cointegrated = p_val < 0.05

    # Hedge ratio via OLS
    X = np.column_stack([pb, np.ones(len(pb))])
    hedge_ratio, intercept = np.linalg.lstsq(X, pa, rcond=None)[0]

    # Spread
    spread = pa - hedge_ratio * pb - intercept
    spread_mean = float(spread.mean())
    spread_std = float(spread.std(ddof=1))
    zscore = ((spread - spread_mean) / spread_std).tolist() if spread_std > 0 else [0.0] * len(spread)

    # Half-life via AR(1) on spread
    spread_lag = spread[:-1]
    spread_diff = np.diff(spread)
    X_ar = np.column_stack([spread_lag, np.ones(len(spread_lag))])
    beta = np.linalg.lstsq(X_ar, spread_diff, rcond=None)[0]
    lambda_val = beta[0]
    half_life = float(-np.log(2) / lambda_val) if lambda_val < 0 else float("inf")

    # Trading signals: entry at |z| > 2, exit at |z| < 0.5
    signals = []
    for z in zscore:
        if z > 2.0:
            signals.append("sell_spread")  # sell A, buy B
        elif z < -2.0:
            signals.append("buy_spread")   # buy A, sell B
        elif abs(z) < 0.5:
            signals.append("exit")
        else:
            signals.append("hold")

    # Johansen test
    try:
        data = np.column_stack([pa, pb])
        joh = coint_johansen(data, det_order=0, k_ar_diff=1)
        johansen_trace_stat = float(joh.lr1[0])
        johansen_crit_95 = float(joh.cvt[0, 1])
        johansen_cointegrated = johansen_trace_stat > johansen_crit_95
    except Exception:
        johansen_trace_stat = 0.0
        johansen_crit_95 = 0.0
        johansen_cointegrated = False

    return {
        "cointegrated": cointegrated,
        "eg_pvalue": round(float(p_val), 4),
        "eg_tstat": round(float(t_stat), 4),
        "johansen_trace_stat": round(johansen_trace_stat, 4),
        "johansen_crit_95": round(johansen_crit_95, 4),
        "johansen_cointegrated": johansen_cointegrated,
        "hedge_ratio": round(float(hedge_ratio), 4),
        "intercept": round(float(intercept), 4),
        "half_life_days": round(half_life, 2) if half_life != float("inf") else 999.0,
        "spread": [round(float(s), 4) for s in spread.tolist()],
        "zscore": [round(float(z), 4) for z in zscore],
        "signals": signals,
        "spread_mean": round(spread_mean, 4),
        "spread_std": round(spread_std, 4),
        "n_buy_signals": signals.count("buy_spread"),
        "n_sell_signals": signals.count("sell_spread"),
    }
