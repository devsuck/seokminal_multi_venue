"""Regime Auto-Wiring (P2.25) — regime_filter HMM 출력을 PortfolioRiskScaler에 연결.

포트폴리오 수익 시계열(as_of 이하) → detect_regime_hmm → current_regime 라벨 →
스케일러가 regime_multipliers로 배수화. HMM 라벨 vocab: bull_low_vol/bull_high_vol/
bear_low_vol/bear_high_vol. 안전: 데이터부족·탐지실패 → 'unknown'(보수 배수).

결정적(HMM random_state=42) · no-lookahead(as_of 절단). detector 주입 가능(테스트).
"""
from __future__ import annotations

KNOWN_REGIMES = {"bull_low_vol", "bull_high_vol", "bear_low_vol", "bear_high_vol"}


def _portfolio_returns(matrix, weights, as_of):
    from jarvis.fusion.backtest import fused_returns
    cal = [d for d in matrix.calendar() if as_of is None or d <= as_of]
    _, series = matrix.aligned(cal)
    if weights:
        series = {k: v for k, v in series.items() if k in weights}
        w = weights
    else:  # 등가중(활동 전략)
        active = {k: v for k, v in series.items() if any(abs(x) > 1e-12 for x in v)}
        series = active
        w = {k: 1.0 / len(series) for k in series} if series else {}
    if not series:
        return []
    return fused_returns(series, w)


def detect_portfolio_regime(matrix, weights: dict | None = None, as_of: str | None = None,
                            method: str = "hmm", min_obs: int = 30, detector=None) -> dict:
    """포트폴리오 레짐 탐지. 반환: {current_regime, method, ...}. 실패=안전 'unknown'."""
    returns = _portfolio_returns(matrix, weights, as_of)
    if len(returns) < min_obs:
        return {"current_regime": "unknown", "method": method,
                "reason": f"insufficient_history(n={len(returns)}<{min_obs})", "n_obs": len(returns)}
    try:
        if detector is not None:
            res = detector(returns)
        elif method == "hmm":
            from regime_filter.hmm_detector import detect_regime_hmm
            res = detect_regime_hmm(returns)
        else:
            raise ValueError(f"unknown method {method}")
    except Exception as exc:  # noqa: BLE001 — 탐지실패 = 안전 폴백
        return {"current_regime": "unknown", "method": method,
                "reason": f"detector_error:{type(exc).__name__}:{exc}", "n_obs": len(returns)}
    label = res.get("current_regime", "unknown")
    if label not in KNOWN_REGIMES:
        label = "unknown"
    return {"current_regime": label, "method": method, "n_obs": len(returns),
            "regime_distribution": res.get("regime_distribution")}


def regime_for_scaler(matrix, weights: dict | None = None, as_of: str | None = None,
                      method: str = "hmm", detector=None) -> dict:
    """스케일러 regime 인자로 바로 넣을 dict(current_regime 키 포함)."""
    return detect_portfolio_regime(matrix, weights, as_of, method, detector=detector)
