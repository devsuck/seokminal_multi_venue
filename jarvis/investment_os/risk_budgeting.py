"""Risk Budgeting & Scenario Analysis — 리스크 예산·시나리오 스트레스. **분석·추천만, 실행 없음.**"""
from __future__ import annotations

_MAX_RISK_CONTRIB = 0.35   # 단일 전략 최대 리스크 기여(예산)
_SCENARIOS = (
    {"name": "rate_shock_+100bp", "equity_shock": -0.08, "vol_mult": 1.3},
    {"name": "vol_spike_2x", "equity_shock": -0.05, "vol_mult": 2.0},
    {"name": "risk_off_drawdown", "equity_shock": -0.15, "vol_mult": 1.8},
    {"name": "liquidity_squeeze", "equity_shock": -0.10, "vol_mult": 1.5},
)


def build_risk_budget(portfolio: dict) -> dict:
    """리스크 예산 — 추천 비중을 리스크 기여로 근사(동일 vol 가정), 단일 전략 상한 점검. 추천만."""
    weights = (portfolio or {}).get("weights") or {}
    if not weights:
        return {"within_budget": True, "contributions": {}, "summary": "no positions",
                "requires_human_review": True, "is_advisory": True, "is_decision": False}
    # 단순 근사: 리스크 기여 ∝ 비중(동일 변동성 가정). 실제 공분산은 데이터 연결 후.
    contrib = {sid: round(w, 4) for sid, w in weights.items()}
    breaches = [sid for sid, c in contrib.items() if c > _MAX_RISK_CONTRIB]
    within = not breaches
    return {"within_budget": within, "contributions": contrib,
            "max_risk_contrib_cap": _MAX_RISK_CONTRIB, "breaches": breaches,
            "summary": f"{len(contrib)} positions, {len(breaches)} over cap",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Risk Budget(추천) — 리스크 기여 근사 + 단일 전략 상한. 실제 공분산은 데이터 연결 후. "
                     "실행/배분 없음.")}


def analyze_scenarios(portfolio: dict, *, notional: float = 0.0) -> dict:
    """시나리오 스트레스 — 고정 시나리오 세트에 추천 포트폴리오 노출 → 가상 손익 영향(추정). 실행 없음."""
    weights = (portfolio or {}).get("weights") or {}
    gross = sum(weights.values()) or 0.0
    results = []
    for sc in _SCENARIOS:
        impact_pct = round(sc["equity_shock"] * gross, 4)
        results.append({"scenario": sc["name"], "portfolio_impact_pct": impact_pct,
                        "vol_multiplier": sc["vol_mult"],
                        "estimated_pnl": round(impact_pct * (notional or 0.0), 2)})
    worst = min(results, key=lambda r: r["portfolio_impact_pct"]) if results else {}
    return {"scenarios": results, "worst_case": worst, "gross_exposure": round(gross, 4),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Scenario Analysis(추정) — 고정 스트레스 시나리오 영향. 가정 기반 추정, 실행 없음. "
                     "실제 충격 파라미터는 데이터/사람 주입.")}
