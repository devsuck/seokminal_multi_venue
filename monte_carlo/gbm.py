"""GBM-based Monte Carlo simulator using Itô's lemma."""
import numpy as np


def run_gbm_monte_carlo(
    returns: list[float],
    horizon_days: int = 252,
    n_simulations: int = 1000,
) -> dict:
    """
    GBM: dS = μS dt + σS dW  →  via Itô: S(t) = S(0) exp((μ - σ²/2)t + σW(t))
    μ = daily drift, σ = daily vol
    """
    ret = np.array(returns)
    mu_daily = ret.mean()
    sigma_daily = ret.std(ddof=1)

    dt = 1  # 1 day steps
    # Itô drift correction: (μ - 0.5σ²)
    drift = mu_daily - 0.5 * sigma_daily ** 2

    np.random.seed(42)
    # Shape: (n_simulations, horizon_days)
    Z = np.random.standard_normal((n_simulations, horizon_days))
    # Daily log-returns under GBM
    log_returns = drift * dt + sigma_daily * np.sqrt(dt) * Z
    # Cumulative price paths (normalized to start at 1.0)
    paths = np.exp(np.cumsum(log_returns, axis=1))
    paths = np.hstack([np.ones((n_simulations, 1)), paths])  # prepend 1.0

    # Sample day indices (up to 20 points for plotting)
    n_pts = min(20, horizon_days + 1)
    day_indices = np.round(np.linspace(0, horizon_days, n_pts)).astype(int).tolist()

    pcts: dict[int, list] = {5: [], 25: [], 50: [], 75: [], 95: []}
    for d in day_indices:
        col = paths[:, d]
        for p in pcts:
            pcts[p].append(round(float(np.percentile(col, p)), 4))

    terminal = paths[:, -1]
    ann_factor = 252 / horizon_days
    ann_returns = (terminal ** ann_factor) - 1

    return {
        "model": "gbm",
        "day_indices": day_indices,
        "paths": {
            "p5": pcts[5],
            "p25": pcts[25],
            "p50": pcts[50],
            "p75": pcts[75],
            "p95": pcts[95],
        },
        "prob_profit": round(float((terminal > 1.0).mean()), 4),
        "prob_loss_20pct": round(float((terminal < 0.8).mean()), 4),
        "terminal_p5": round(float(np.percentile(terminal, 5)), 4),
        "terminal_p25": round(float(np.percentile(terminal, 25)), 4),
        "terminal_median": round(float(np.median(terminal)), 4),
        "terminal_p75": round(float(np.percentile(terminal, 75)), 4),
        "terminal_p95": round(float(np.percentile(terminal, 95)), 4),
        "ann_return_mean": round(float(ann_returns.mean()), 4),
        "ann_return_p5": round(float(np.percentile(ann_returns, 5)), 4),
        "ann_return_p95": round(float(np.percentile(ann_returns, 95)), 4),
        "max_dd_mean": 0.0,  # simplified
        "max_dd_p95": 0.0,
        "mu_daily": round(float(mu_daily), 6),
        "sigma_daily": round(float(sigma_daily), 6),
        "ito_drift_correction": round(float(0.5 * sigma_daily ** 2), 6),
    }
