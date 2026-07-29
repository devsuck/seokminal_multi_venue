"""Jarvis Investment Research OS v1.0 (P95) — 최종 통합 콕핏. **읽기 전용. 사람이 모든 결정.**

Market State → Research Opportunities → Active Experiments → Validation Status → Risk →
Portfolio Context → Decision Queue → Knowledge Growth. 기존 콕핏(P85)에 시장 지능(P86-88)을 더한
최종 운영 화면. 모두 기존 orchestration 재사용 — 새 로직 없음.

원칙(문서 §Constitution, §P95): 통합·시각화만. 결정적. 거래·집행·자본배분·배포 승인 없음.
"""
from __future__ import annotations


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_market_cockpit(indicators: dict | None = None, signals: dict | None = None) -> dict:
    """시장 지능 v1.0 콕핏(읽기전용) — 기존 cockpit + regime + opportunity 조율."""
    from jarvis.research_workflow.cockpit import build_cockpit
    base = _safe(build_cockpit, {})

    from jarvis.research_workflow.regime import detect_regime
    market_state = _safe(lambda: detect_regime(indicators or {}), {"regime": "UNKNOWN"})

    from jarvis.research_workflow.opportunity_discovery import discover
    opportunities = _safe(lambda: discover(signals or {}), {"opportunities": [], "count": 0})

    # 흐름 순서(문서 §P95)
    return {
        "market_state": {"regime": market_state.get("regime"), "confidence": market_state.get("confidence"),
                         "labels": market_state.get("labels", []),
                         "recommended_research": market_state.get("recommended_research", []),
                         "avoid": market_state.get("avoid", []),
                         "historical_similar_periods": market_state.get("historical_similar_periods", [])},
        "research_opportunities": opportunities.get("opportunities", []),
        "active_experiments": base.get("current_loop", {}),
        "validation_status": {"health": base.get("research_health", {}).get("overall_health_score"),
                              "coverage": base.get("research_health", {}).get("coverage", {}),
                              "incomplete": base.get("research_health", {}).get("incomplete_research")},
        "risk": base.get("highest_risks", {}),
        "portfolio_context": base.get("portfolio_exposure", {}),
        "decision_queue": base.get("human_review_queue", []),
        "knowledge_growth": base.get("knowledge_growth", {}),
        "timeline": base.get("timeline", []),
        "top_opportunities": base.get("top_opportunities", []),
        "recent_sessions": base.get("recent_sessions", []),
        "quick_resume": base.get("quick_resume", []),
        "health_score": base.get("health_score", 0),
        "is_advisory": True, "is_decision": False,
        "disclaimer": ("Jarvis Investment Research OS v1.0 — READ ONLY. 시장 관찰·기회 발견·증거 평가·"
                       "불확실성 설명·사람 의사결정 지원. 절대 거래·자본배분·배포 승인 없음. 사람이 모든 결정을 한다.")}
