"""Hurst exponent via rescaled range (R/S) analysis."""
import numpy as np


def compute_hurst(prices: list[float], min_lag=10, max_lag=None, n_lags=20) -> dict:
    prices = np.array(prices, dtype=float)
    returns = np.diff(np.log(prices))
    n = len(returns)
    if max_lag is None:
        max_lag = n // 2
    lags = np.unique(np.logspace(np.log10(min_lag), np.log10(max_lag), n_lags).astype(int))
    rs_values = []
    valid_lags = []
    for lag in lags:
        if lag >= n:
            continue
        chunks = [returns[i:i+lag] for i in range(0, n - lag + 1, lag)]
        chunk_rs = []
        for chunk in chunks:
            mean = chunk.mean()
            deviation = np.cumsum(chunk - mean)
            r = deviation.max() - deviation.min()
            s = chunk.std(ddof=1)
            if s > 0:
                chunk_rs.append(r / s)
        if chunk_rs:
            rs_values.append(np.mean(chunk_rs))
            valid_lags.append(int(lag))
    if len(valid_lags) < 2:
        return {"hurst": 0.5, "interpretation": "insufficient data", "lags": [], "rs_values": []}
    log_lags = np.log(valid_lags)
    log_rs = np.log(rs_values)
    hurst = float(np.polyfit(log_lags, log_rs, 1)[0])
    if hurst > 0.55:
        interp = "trending (persistent)"
    elif hurst < 0.45:
        interp = "mean-reverting (anti-persistent)"
    else:
        interp = "random walk"
    return {
        "hurst": round(hurst, 4),
        "interpretation": interp,
        "lags": valid_lags,
        "rs_values": [round(v, 4) for v in rs_values],
    }
