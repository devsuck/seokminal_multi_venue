"""Black-Litterman model for portfolio optimization."""
import numpy as np
from scipy.optimize import minimize


def compute_black_litterman(
    returns_matrix: np.ndarray,
    instrument_ids: list[str],
    views: list[dict],  # [{"instrument": str, "expected_return": float, "confidence": float}]
    tau: float = 0.05,
    risk_aversion: float = 2.5,
) -> dict:
    """
    Black-Litterman model.
    views: list of absolute return views with confidence levels.
    """
    n = returns_matrix.shape[1]
    cov = np.cov(returns_matrix.T) * 252
    mean_returns = returns_matrix.mean(axis=0) * 252

    # Market-cap weights proxy: equal weight as prior
    w_mkt = np.ones(n) / n

    # Implied equilibrium returns (reverse optimization)
    pi = risk_aversion * cov @ w_mkt  # prior expected returns

    if not views:
        # No views: return prior (Markowitz with implied returns)
        return _optimize_with_returns(pi, cov, instrument_ids, "black-litterman (no views)")

    # Build P (picking matrix) and Q (views vector) and Omega (uncertainty)
    k = len(views)
    P = np.zeros((k, n))
    Q = np.zeros(k)
    Omega = np.zeros((k, k))

    inst_idx = {iid: i for i, iid in enumerate(instrument_ids)}

    for j, view in enumerate(views):
        inst = view.get("instrument", "")
        if inst in inst_idx:
            P[j, inst_idx[inst]] = 1.0
        Q[j] = view.get("expected_return", 0.0)
        conf = max(min(view.get("confidence", 0.5), 0.99), 0.01)
        # Omega diagonal: uncertainty inversely proportional to confidence
        Omega[j, j] = (1 - conf) / conf * (tau * float(P[j] @ cov @ P[j]))

    # BL posterior expected returns
    tau_sigma = tau * cov
    M = np.linalg.inv(np.linalg.inv(tau_sigma) + P.T @ np.linalg.inv(Omega) @ P)
    mu_bl = M @ (np.linalg.inv(tau_sigma) @ pi + P.T @ np.linalg.inv(Omega) @ Q)
    sigma_bl = cov + M

    result = _optimize_with_returns(mu_bl, sigma_bl, instrument_ids, "black-litterman")
    result["prior_returns"] = {iid: round(float(pi[i]), 4) for i, iid in enumerate(instrument_ids)}
    result["posterior_returns"] = {iid: round(float(mu_bl[i]), 4) for i, iid in enumerate(instrument_ids)}
    return result


def _optimize_with_returns(mu, cov, instrument_ids, model_name):
    n = len(instrument_ids)

    def neg_sharpe(w):
        ret = float(w @ mu)
        vol = float(np.sqrt(w @ cov @ w))
        return -ret / vol if vol > 0 else 0.0

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(0.0, 1.0)] * n
    w0 = np.ones(n) / n
    result = minimize(neg_sharpe, w0, method="SLSQP", bounds=bounds, constraints=constraints)
    w = result.x
    vol = float(np.sqrt(w @ cov @ w))
    ret = float(w @ mu)
    return {
        "model": model_name,
        "weights": {iid: round(float(wi), 4) for iid, wi in zip(instrument_ids, w)},
        "expected_return": round(ret, 4),
        "expected_vol": round(vol, 4),
        "sharpe": round(ret / vol, 4) if vol > 0 else 0.0,
        "converged": bool(result.success),
    }
