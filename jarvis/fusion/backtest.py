"""Fusion Backtest Validation — 개별 전략 vs 융합 포트폴리오 신호 성과 비교.

목적: 융합이 실제로 리스크조정 성과·분산을 개선하는지 결정적으로 검증.
지표: Sharpe · CAGR · MaxDrawdown · Turnover · Correlation reduction.

입력 = 전략별 정렬된 수익률 시퀀스(길이 다르면 최근 기준 절단). 신규 전략 추가 아님 —
기존 검증전략의 수익률만 비교. 실데이터가 1개 전략뿐이면 분산지표는 n/a(정직).
"""
from __future__ import annotations

import statistics

from risk_analysis.metrics import compute_risk_metrics


def _align(returns_by_strategy: dict[str, list[float]]) -> dict[str, list[float]]:
    """길이 다른 시퀀스를 공통 최소길이로 최근절단(정렬 가정)."""
    series = {k: v for k, v in returns_by_strategy.items() if len(v) >= 2}
    if not series:
        return {}
    n = min(len(v) for v in series.values())
    return {k: v[-n:] for k, v in series.items()}


def _metrics(returns: list[float]) -> dict:
    m = compute_risk_metrics(returns)
    return {"sharpe": m["sharpe_ratio"], "cagr": m["annualized_return"],
            "max_drawdown": m["max_drawdown"], "volatility": m["volatility"],
            "n": m["observation_count"]}


def _equal_weights(keys) -> dict[str, float]:
    w = 1.0 / len(keys)
    return {k: w for k in keys}


def fused_returns(series: dict[str, list[float]], weights: dict[str, float]) -> list[float]:
    """가중합 포트폴리오 수익률 시퀀스(매기 리밸런스)."""
    keys = list(series.keys())
    n = len(next(iter(series.values())))
    tot = sum(weights.get(k, 0.0) for k in keys) or 1.0
    w = {k: weights.get(k, 0.0) / tot for k in keys}
    return [sum(w[k] * series[k][t] for k in keys) for t in range(n)]


def avg_pairwise_corr(series: dict[str, list[float]]) -> float | None:
    keys = list(series.keys())
    if len(keys) < 2:
        return None
    cs = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            try:
                cs.append(statistics.correlation(series[keys[i]], series[keys[j]]))
            except statistics.StatisticsError:
                pass
    return round(statistics.mean(cs), 6) if cs else None


def diversification(series: dict[str, list[float]], weights: dict[str, float]) -> dict:
    """분산 이득: DR = Σwσ / σ_port(≥1). corr_reduction = 1 - σ_port/Σwσ."""
    keys = list(series.keys())
    if len(keys) < 2:
        return {"diversification_ratio": None, "corr_reduction": None,
                "avg_pairwise_corr": None, "note": "분산지표는 전략 ≥2 필요"}
    tot = sum(weights.get(k, 0.0) for k in keys) or 1.0
    w = {k: weights.get(k, 0.0) / tot for k in keys}
    weighted_vol = sum(w[k] * statistics.stdev(series[k]) for k in keys)
    port_vol = statistics.stdev(fused_returns(series, weights))
    dr = (weighted_vol / port_vol) if port_vol > 1e-12 else None
    return {"diversification_ratio": round(dr, 4) if dr else None,
            "corr_reduction": round(1 - port_vol / weighted_vol, 4) if weighted_vol > 1e-12 else None,
            "avg_pairwise_corr": avg_pairwise_corr(series)}


def turnover(position_series: list[dict[str, float]]) -> float | None:
    """포지션(계기→부호가중) 시계열의 평균 회전율 = mean(Σ|Δw|)/2."""
    if len(position_series) < 2:
        return None
    tos = []
    for prev, cur in zip(position_series, position_series[1:]):
        keys = set(prev) | set(cur)
        tos.append(sum(abs(cur.get(k, 0.0) - prev.get(k, 0.0)) for k in keys) / 2.0)
    return round(statistics.mean(tos), 6) if tos else None


def compare_performance(returns_by_strategy: dict[str, list[float]],
                        weights: dict[str, float] | None = None,
                        position_series: dict[str, list[dict]] | None = None) -> dict:
    """개별 vs 융합 성과 비교 리포트.

    weights=None → 등가중. position_series 주면 turnover 계산(개별+융합).
    """
    series = _align(returns_by_strategy)
    if not series:
        return {"error": "no_strategy_with_>=2_returns", "individual": {}, "fused": None}
    weights = weights or _equal_weights(series.keys())

    individual = {k: _metrics(v) for k, v in series.items()}
    if position_series:
        for k in individual:
            if k in position_series:
                individual[k]["turnover"] = turnover(position_series[k])

    fret = fused_returns(series, weights)
    fused = _metrics(fret)
    fused["weights"] = {k: round(weights.get(k, 0.0), 6) for k in series}
    fused.update(diversification(series, weights))

    # 융합 성과가 개별 평균 대비 개선됐는지(설명가능 요약)
    ind_sharpes = [m["sharpe"] for m in individual.values() if m["sharpe"] is not None]
    fused["sharpe_vs_avg_individual"] = (
        round(fused["sharpe"] - statistics.mean(ind_sharpes), 4)
        if fused["sharpe"] is not None and ind_sharpes else None)
    return {"n_strategies": len(series), "n_obs": len(fret),
            "individual": individual, "fused": fused}
