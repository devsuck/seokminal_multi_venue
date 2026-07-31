"""Human Decision Center (P93) — 투자위원회 스타일 워크스페이스. **사람이 결정, 엔진은 조직만.**

thesis·evidence·counter arguments·risk analysis·historical similarity·portfolio impact·confidence·
decision history 를 하나로 묶는다. 사람 입력(decision·reason·timestamp)은 **기존 감사 시스템(rwf_runs
HUMAN_DECISION)** 으로 저장. **재사용**: decision_support(P65)·council_evolution(P90)·risk report(P62).

원칙(문서 §Constitution, §P93): 통합·조율만. 새 저장소 없음. 엔진은 승인/집행하지 않는다 — reviewer 필수.
"""
from __future__ import annotations


def committee_packet(question, *, topic=None, metrics=None, portfolio=None, strategies=None,
                     backtest=None, assistant=None, reader=None) -> dict:
    """투자위원회 패킷(결정적, 읽기전용) — 논지·근거·반론·리스크·과거유사·포트폴리오·신뢰도·이력."""
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine(reader)
    t = topic or question

    from jarvis.research_workflow.decision_support import DecisionSupportEngine
    memo = DecisionSupportEngine(assistant=assistant).build_memo(
        question, topic=t, metrics=metrics, portfolio=portfolio, strategies=strategies,
        backtest=backtest).to_dict()

    from jarvis.research_workflow.council_evolution import deliberate
    council = deliberate(question, assistant=assistant)

    decision_history = _decision_history(t)
    return {"question": question, "thesis": memo.get("rationale") or memo.get("recommendation"),
            "rationale": memo.get("rationale"), "evidence": memo.get("evidence"),
            "supporting_arguments": memo.get("supporting_arguments"),
            "counter_arguments": memo.get("counter_arguments"),
            "risk_summary": memo.get("risk_summary"),
            "historical_similar_cases": memo.get("historical_similar_cases"),
            "portfolio_impact": memo.get("portfolio_impact"),
            "confidence": memo.get("confidence"), "confidence_breakdown": memo.get("confidence_breakdown"),
            "remaining_unknowns": memo.get("remaining_unknowns"),
            "council": {"perspectives": council.get("expanded_perspectives"),
                        "recommendation": council.get("recommendation"),
                        "conflicts": council.get("conflicts")},
            "decision_history": decision_history,
            "requires_human_decision": True, "is_advisory": True, "is_decision": False,
            "note": "투자위원회 패킷 — 증거 조직·자문. 결정·이유·시각은 사람이 입력, 기존 감사로 저장."}


def _decision_history(topic: str) -> list:
    """기존 감사(rwf_runs HUMAN_DECISION + ras_ notes)에서 결정 이력 회수(읽기전용)."""
    out = []
    try:
        from jarvis.research_workflow import ledger as wl
        for e in wl.read_runs():
            if e.get("stage") == "HUMAN_DECISION" and e.get("status") == "COMPLETED":
                out.append({"source": "rwf_runs", "run_id": e.get("run_id"),
                            "note": e.get("note", ""), "at": e.get("occurred_at", "")})
    except Exception:  # noqa: BLE001
        pass
    return out[-20:]


def record_decision(run_id: str, decision: str, reason: str, reviewer: str, *,
                    now: str = "", commit: bool = False) -> dict:
    """사람 결정 기록 — **기존 감사 시스템(WorkflowOrchestrator.record_human_decision)** 재사용. reviewer 필수."""
    if not str(reviewer or "").strip():
        return {"error": "reviewer(사람) 필수 — 엔진은 자동 승인하지 않는다."}
    from jarvis.research_workflow.orchestrator import WorkflowOrchestrator
    rec = WorkflowOrchestrator().record_human_decision(
        run_id, decision, reviewer, note=reason, now=now, commit=commit)
    return {"recorded": True, "decision": rec.get("decision"), "reviewer": reviewer,
            "is_human": rec.get("is_human"), "run_id": run_id, "reason": reason,
            "is_decision": False, "note": "사람 결정을 기존 rwf_runs 감사에 기록(새 저장소 없음)."}
