"""Strategy Laboratory (P91) — 전략을 **재사용 가능한 연구 객체**로 표현한다. **읽기 전용, 결정적.**

Strategy DNA: factors·universe·time horizon·entry·exit·risk model·validation method·failure history·
successful regimes. 유사 전략 찾기·비교·반복 실수 식별. **재사용**: experiment_tracking·failure
intelligence·knowledge graph·cross_strategy(P83)·quality_score(P84)·risk report(P62).

원칙(문서 §Constitution, §P91): 통합·조율만. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def strategy_dna(name: str, *, spec: dict | None = None, assistant=None) -> dict:
    """전략 DNA(결정적) — 기존 실험/실패/리스크/검증에서 조립. 읽기전용."""
    n = str(name or "unknown_strategy")
    sp = spec or {}
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()

    # 실패 이력 — mistake_check 재사용
    failure_history = {}
    try:
        mc = assistant.mistake_check(n)
        failure_history = {"count": mc.get("failure_count", 0), "by_category": mc.get("by_category", {})}
    except Exception:  # noqa: BLE001
        pass
    # 리스크 모델/유형 — StrategyRiskReasoner 재사용
    risk_type, risk_model = "generic", {}
    try:
        from jarvis.research_risk_intelligence.failure_reasoning import StrategyRiskReasoner
        rep = StrategyRiskReasoner().risk_report(n, sp.get("metrics"))
        risk_type = rep.strategy_type
        risk_model = {"main_risk": rep.main_risk, "weakness": rep.weakness, "category_flags": rep.category_flags}
    except Exception:  # noqa: BLE001
        pass
    # 성공 레짐 — 리스크 유형 → 유리 레짐(regime 모듈 재사용)
    successful_regimes = []
    try:
        from jarvis.research_workflow.regime import _FAVORABLE
        for reg, strats in _FAVORABLE.items():
            if any(risk_type in s or s in risk_type for s in strats) or risk_type in " ".join(strats):
                successful_regimes.append(reg)
    except Exception:  # noqa: BLE001
        pass

    return {"strategy": n, "type": risk_type,
            "dna": {"factors": sp.get("features", sp.get("factors", [])),
                    "universe": sp.get("universe", ""), "time_horizon": sp.get("timeframe", sp.get("horizon", "")),
                    "entry_logic": sp.get("entry_rules", sp.get("entry", "")),
                    "exit_logic": sp.get("exit_rules", sp.get("exit", "")),
                    "risk_model": risk_model,
                    "validation_method": sp.get("validation_checklist", "walk-forward + OOS + random baseline"),
                    "failure_history": failure_history,
                    "successful_regimes": sorted(set(successful_regimes))},
            "is_advisory": True, "is_decision": False,
            "note": "Strategy DNA — 기존 실험/실패/리스크 재조립(읽기전용). 거래·집행 없음."}


def find_similar(name: str, *, candidates=None, assistant=None) -> dict:
    """유사 전략 찾기 — cross_strategy 재사용."""
    from jarvis.research_workflow.cross_strategy import compare
    base = {"name": name}
    cands = candidates or []
    scored = [{"strategy": c.get("name", "?"), **compare(base, c, assistant=assistant)} for c in cands]
    scored.sort(key=lambda x: -x.get("similarity", 0))
    return {"strategy": name, "similar": scored, "count": len(scored),
            "is_advisory": True, "is_decision": False}


def repeated_mistakes(name: str, *, assistant=None) -> dict:
    """반복 실수 식별 — failure intelligence 재사용."""
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    mc = assistant.mistake_check(name)
    return {"strategy": name, "made_this_mistake": mc.get("made_this_mistake", False),
            "failure_count": mc.get("failure_count", 0), "by_category": mc.get("by_category", {}),
            "headline": mc.get("headline", ""), "is_advisory": True, "is_decision": False}
