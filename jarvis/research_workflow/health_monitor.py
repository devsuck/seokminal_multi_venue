"""Research Health Monitor (P81) — 결정적 운영 지표. **읽기 전용, 새 저장소 없음.**

기존 원장/엔진에서 활성 연구·대기 검토·검증 누락·불완전 연구·지식 성장·실패 분포·연구 속도·커버리지·
전체 건강 점수를 결정적으로 계산한다. 통합·관측만 — 새 지표 저장소를 만들지 않는다.
"""
from __future__ import annotations


def _read(mod_name, fn_name):
    try:
        mod = __import__(mod_name, fromlist=[fn_name])
        return list(getattr(mod, fn_name)() or [])
    except Exception:  # noqa: BLE001
        return []


def build_health() -> dict:
    """운영 건강 지표(결정적). 기존 원장/어시스턴트 재사용."""
    ring = _read("jarvis.research_ingestion.ledger", "read_ingestions")
    loops = _read("jarvis.research_workflow.ledger", "read_loops")
    runs = _read("jarvis.research_workflow.ledger", "read_runs")
    lessons = _read("jarvis.research_memory_intelligence.ledger", "read_lessons")
    successes = _read("jarvis.research_memory_intelligence.ledger", "read_successes")
    failures = _read("jarvis.research_memory_intelligence.ledger", "read_failures")
    memories = _read("jarvis.research_memory_intelligence.ledger", "read_memory_events")

    # 활성 루프(비종결)
    loop_ids = {e.get("loop_id") for e in loops}
    active_research = len(loop_ids)
    # 사람 검토 대기 — 워크플로 DECISION 후 HUMAN 미완
    run_ids = {e.get("run_id") for e in runs}
    awaiting = 0
    for rid in run_ids:
        evs = [e for e in runs if e.get("run_id") == rid]
        has_dec = any(e.get("stage") == "DECISION" and e.get("status") == "COMPLETED" for e in evs)
        has_hum = any(e.get("stage") == "HUMAN_DECISION" and e.get("status") == "COMPLETED" for e in evs)
        if has_dec and not has_hum:
            awaiting += 1

    incomplete = [r for r in ring if r.get("validation_complete") is False]
    knowledge_count = len(lessons) + len(successes) + len(memories)

    # 실패 분포(재사용)
    try:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        fi = ResearchAssistantEngine().failure_intelligence()
        failure_distribution = fi.by_category
        total_failures = fi.total_failures
    except Exception:  # noqa: BLE001
        failure_distribution, total_failures = {}, len(failures)

    ingested = len(ring)
    velocity = len(loops) + ingested          # 누적 활동량(결정적 프록시)

    # 커버리지(0..1)
    complete = sum(1 for r in ring if r.get("validation_complete"))
    memory_coverage = 1.0 if knowledge_count else 0.0
    risk_coverage = round(min(1.0, len([r for r in ring if r.get("outcome")]) / max(1, ingested)), 4)
    portfolio_coverage = round(min(1.0, len([l for l in lessons
                                             if str(l.get("impact")) == "portfolio"]) / max(1, ingested)), 4) if ingested else 0.0
    validation_coverage = round(complete / ingested, 4) if ingested else 0.0

    # 전체 건강 점수(0..100, 결정적 가중)
    parts = {
        "validation": validation_coverage,
        "memory": 1.0 if knowledge_count else 0.0,
        "review_backlog": 1.0 - min(1.0, awaiting / 10.0),
        "incompleteness": 1.0 - (len(incomplete) / ingested if ingested else 0.0),
        "activity": min(1.0, velocity / 20.0),
    }
    weights = {"validation": 0.3, "memory": 0.2, "review_backlog": 0.15,
               "incompleteness": 0.2, "activity": 0.15}
    score = round(sum(parts[k] * weights[k] for k in weights) * 100, 1)
    trend = "GROWING" if knowledge_count >= 5 else "EARLY" if knowledge_count else "EMPTY"
    band = "HEALTHY" if score >= 70 else "FAIR" if score >= 40 else "ATTENTION"

    return {
        "active_research": active_research, "waiting_human_review": awaiting,
        "validation_missing": len(incomplete), "incomplete_research": len(incomplete),
        "knowledge_growth": knowledge_count, "failure_distribution": failure_distribution,
        "total_failures": total_failures, "research_velocity": velocity,
        "coverage": {"validation": validation_coverage, "portfolio": portfolio_coverage,
                     "risk": risk_coverage, "memory": memory_coverage},
        "score_components": parts, "overall_health_score": score, "health_band": band,
        "trend": trend, "is_advisory": True, "is_decision": False,
        "note": "기존 원장 파생 결정적 운영 지표 — 새 저장소 없음."}
