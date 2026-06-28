"""Monte Carlo simulation via bootstrap resampling (numpy only)."""
import math
import numpy as np


def run_monte_carlo(
    returns: list[float],
    horizon_days: int = 252,
    n_simulations: int = 1000,
    starting_value: float = 1.0,
    seed: int | None = 42,
) -> dict:
    """
    Bootstrap Monte Carlo over `horizon_days` using historical daily returns.

    Returns percentile equity paths + summary statistics.
    """
    if len(returns) < 10:
        raise ValueError(f"need at least 10 return observations, got {len(returns)}")

    rng = np.random.default_rng(seed)
    arr = np.array(returns, dtype=np.float64)

    # Shape: (n_simulations, horizon_days)
    sampled = rng.choice(arr, size=(n_simulations, horizon_days), replace=True)

    # Cumulative product: equity curves from 1.0
    equity = np.cumprod(1.0 + sampled, axis=1) * starting_value

    # Percentile paths (sparse: every ~5 days to keep payload small)
    step = max(1, horizon_days // 50)
    indices = list(range(0, horizon_days, step))
    if indices[-1] != horizon_days - 1:
        indices.append(horizon_days - 1)

    pct_paths: dict[str, list[float]] = {}
    for pct_label, pct_val in [("p5", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95)]:
        pct_paths[pct_label] = [round(float(np.percentile(equity[:, i], pct_val)), 6) for i in indices]

    final_values = equity[:, -1]

    # Max drawdown per simulation
    peak = np.maximum.accumulate(equity, axis=1)
    drawdowns = (peak - equity) / np.where(peak > 0, peak, 1)
    max_dds = np.max(drawdowns, axis=1)

    # Annualized return per simulation
    ann_returns = final_values ** (252.0 / horizon_days) - 1.0

    return {
        "n_simulations": n_simulations,
        "horizon_days": horizon_days,
        "starting_value": starting_value,
        "day_indices": indices,
        "paths": pct_paths,
        # terminal stats
        "terminal_mean": float(np.mean(final_values)),
        "terminal_median": float(np.median(final_values)),
        "terminal_p5": float(np.percentile(final_values, 5)),
        "terminal_p95": float(np.percentile(final_values, 95)),
        "prob_profit": float(np.mean(final_values > starting_value)),
        "prob_loss_20pct": float(np.mean(final_values < starting_value * 0.8)),
        # annualized
        "ann_return_mean": float(np.mean(ann_returns)),
        "ann_return_p5": float(np.percentile(ann_returns, 5)),
        "ann_return_p95": float(np.percentile(ann_returns, 95)),
        # drawdown
        "max_dd_mean": float(np.mean(max_dds)),
        "max_dd_p95": float(np.percentile(max_dds, 95)),
    }
