import numpy as np
from scipy.optimize import minimize


PERIODS_PER_YEAR = 252


def markowitz_optimize(
    returns_map: dict[str, list[float]],
    risk_free_rate: float = 0.0,
) -> dict:
    """
    Compute minimum-variance and max-Sharpe portfolios.

    Args:
        returns_map: {instrument_id: [daily_returns]} — all lists same length.
        risk_free_rate: Annual risk-free rate (decimal).

    Returns dict with:
        min_variance: {weights, expected_return, volatility}
        max_sharpe:   {weights, expected_return, volatility, sharpe}
        instruments:  list of instrument_ids (matches weight order)
        efficient_frontier: list of {expected_return, volatility} points
    """
    instruments = list(returns_map.keys())
    n = len(instruments)
    if n < 2:
        raise ValueError(f"need at least 2 instruments, got {n}")

    matrix = np.array([returns_map[k] for k in instruments], dtype=float)

    mean_returns = matrix.mean(axis=1)
    cov = np.cov(matrix)
    ann_mean = mean_returns * PERIODS_PER_YEAR
    ann_cov = cov * PERIODS_PER_YEAR

    def portfolio_vol(w: np.ndarray) -> float:
        return float(np.sqrt(w @ ann_cov @ w))

    def neg_sharpe(w: np.ndarray) -> float:
        ret = float(w @ ann_mean)
        vol = portfolio_vol(w)
        return -(ret - risk_free_rate) / vol if vol > 1e-10 else 0.0

    constraints = {"type": "eq", "fun": lambda w: w.sum() - 1}
    bounds = [(0.0, 1.0)] * n
    w0 = np.ones(n) / n

    # Min variance
    mv_result = minimize(portfolio_vol, w0, method="SLSQP", bounds=bounds, constraints=constraints)
    mv_w = mv_result.x
    mv_ret = float(mv_w @ ann_mean)
    mv_vol = portfolio_vol(mv_w)

    # Max Sharpe
    ms_result = minimize(neg_sharpe, w0, method="SLSQP", bounds=bounds, constraints=constraints)
    ms_w = ms_result.x
    ms_ret = float(ms_w @ ann_mean)
    ms_vol = portfolio_vol(ms_w)
    ms_sharpe = (ms_ret - risk_free_rate) / ms_vol if ms_vol > 1e-10 else None

    # Efficient frontier (20 points between min-vol return and max return)
    min_ret = mv_ret
    max_ret = float(ann_mean.max())
    frontier = []
    for target in np.linspace(min_ret, max_ret, 20):
        cons = [
            {"type": "eq", "fun": lambda w: w.sum() - 1},
            {"type": "eq", "fun": lambda w, t=target: float(w @ ann_mean) - t},
        ]
        res = minimize(portfolio_vol, w0, method="SLSQP", bounds=bounds, constraints=cons)
        if res.success:
            frontier.append({
                "expected_return": target,
                "volatility": portfolio_vol(res.x),
            })

    def weights_dict(w: np.ndarray) -> dict[str, float]:
        return {instruments[i]: round(float(w[i]), 6) for i in range(n)}

    return {
        "instruments": instruments,
        "min_variance": {
            "weights": weights_dict(mv_w),
            "expected_return": mv_ret,
            "volatility": mv_vol,
        },
        "max_sharpe": {
            "weights": weights_dict(ms_w),
            "expected_return": ms_ret,
            "volatility": ms_vol,
            "sharpe": ms_sharpe,
        },
        "efficient_frontier": frontier,
    }
