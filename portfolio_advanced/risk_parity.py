"""Risk Parity portfolio construction."""
import numpy as np
from scipy.optimize import minimize


def compute_risk_parity(returns_matrix: np.ndarray, instrument_ids: list[str]) -> dict:
    """
    Risk parity: each asset contributes equally to total portfolio risk.
    returns_matrix: shape (T, N) — T days, N assets
    """
    n = returns_matrix.shape[1]
    cov = np.cov(returns_matrix.T) * 252  # annualized

    def portfolio_vol(w):
        return float(np.sqrt(w @ cov @ w))

    def risk_contribution(w):
        pv = portfolio_vol(w)
        if pv == 0:
            return np.zeros(n)
        marginal = cov @ w
        return w * marginal / pv

    def risk_parity_objective(w):
        rc = risk_contribution(w)
        target = portfolio_vol(w) / n
        return float(np.sum((rc - target) ** 2))

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(0.001, 1.0)] * n
    w0 = np.ones(n) / n

    result = minimize(
        risk_parity_objective, w0,
        method="SLSQP", bounds=bounds, constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-9},
    )

    w = result.x
    rc = risk_contribution(w)
    pv = portfolio_vol(w)
    mean_returns = returns_matrix.mean(axis=0) * 252
    expected_return = float(w @ mean_returns)

    return {
        "weights": {iid: round(float(wi), 4) for iid, wi in zip(instrument_ids, w)},
        "risk_contribution": {iid: round(float(rc_i / pv), 4) for iid, rc_i in zip(instrument_ids, rc)},
        "expected_return": round(expected_return, 4),
        "expected_vol": round(pv, 4),
        "sharpe": round(expected_return / pv, 4) if pv > 0 else 0.0,
        "converged": bool(result.success),
    }
