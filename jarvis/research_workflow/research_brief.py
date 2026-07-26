"""Autonomous Research Brief (P189) — Daily Research Brief 생성. **요약만, 실행 없음.**

7섹션: ① Market Changes ② New Research Opportunities ③ New Hypotheses ④ Pending Experiments
⑤ Validation Results ⑥ Failed Research Lessons ⑦ Human Review Queue.

**재사용**: morning_briefing(P142)·market_observation(P182)·hypothesis_discovery(P183)·
research_gate(P186)·research_ingestion(실패 교훈). 새 원장 없음.
원칙(문서 §Constitution, §P189): 통합·조율만 · 결정적 · 자문 전용 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_research_brief(*, topic: str = "", signals=None, limit: int = 6) -> dict:
    """Daily Research Brief(7섹션) — 관찰·기회·가설·대기실험·검증·실패교훈·검토큐. 결정적·읽기전용."""
    # ① Market Changes (morning_briefing 재사용)
    briefing = _safe(lambda: __import__("jarvis.research_workflow.morning_briefing",
                                        fromlist=["generate"]).generate(), {}) or {}
    # ② New Research Opportunities
    obs = _safe(lambda: __import__("jarvis.research_workflow.market_observation",
                                   fromlist=["observe_market"]).observe_market(signals=signals), {}) or {}
    top_opp = (obs.get("opportunities") or [{}])[0] if obs.get("opportunities") else {}
    # ③ New Hypotheses
    disc = _safe(lambda: __import__("jarvis.research_workflow.hypothesis_discovery",
                                    fromlist=["discover_research"]
                                    ).discover_research(topic, opportunity=top_opp, limit=limit), {}) or {}
    research_hyps = disc.get("research_hypotheses", [])
    # ④ Pending Experiments (approval queue)
    prio = _safe(lambda: __import__("jarvis.research_workflow.research_priority",
                                    fromlist=["prioritize_research"]
                                    ).prioritize_research(research_hyps, limit=limit), {}) or {}
    gate = _safe(lambda: __import__("jarvis.research_workflow.research_gate",
                                    fromlist=["build_approval_queue"]
                                    ).build_approval_queue(prio.get("research_queue", []), limit=limit), {}) or {}
    # ⑤ Validation Results + ⑥ Failed Research Lessons (수집 요약)
    summ = _safe(lambda: __import__("jarvis.research_ingestion.engine",
                                    fromlist=["ResearchIngestionEngine"]
                                    ).ResearchIngestionEngine().summary(), None)
    by_outcome = (getattr(summ, "by_outcome", None) or {}) if summ else {}
    by_failcat = (getattr(summ, "by_failure_category", None) or {}) if summ else {}

    return {"sections": {
                "market_changes": {"summary": briefing.get("summary") or briefing.get("headline", ""),
                                   "regime": (obs.get("by_type") or {})},
                "new_research_opportunities": {"count": obs.get("opportunity_count", 0),
                                               "top": {"type": top_opp.get("type"),
                                                       "observation": top_opp.get("observation"),
                                                       "questions": top_opp.get("possible_questions", [])}},
                "new_hypotheses": {"count": len(research_hyps),
                                   "top": [h.get("question") for h in research_hyps[:3]]},
                "pending_experiments": {"queue_size": gate.get("queue_size", 0),
                                        "requests": [{"question": r["question"],
                                                      "priority_score": r["priority_score"]}
                                                     for r in gate.get("requests", [])[:5]]},
                "validation_results": {"by_outcome": by_outcome},
                "failed_research_lessons": {"by_failure_category": by_failcat},
                "human_review_queue": {"pending": gate.get("queue_size", 0),
                                       "actions": gate.get("available_actions", [])},
            },
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Autonomous Research Brief(읽기전용) — 7섹션 일일 브리프. 기존 모듈 조율. "
                     "새 원장 없음, 자동 실행 없음. 사람이 검토·결정.")}
