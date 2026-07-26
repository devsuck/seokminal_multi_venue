"""Research Intelligence Metrics v3 (P196) — 자율 연구 루프 지표. **측정만, 실행 없음.**

지표: generated_hypotheses·accepted_research_proposals·completed_experiments·validation_success_rate·
avoided_duplicate_research·knowledge_reuse_rate·failure_prevention_count.

**재사용**: research_ingestion(요약)·knowledge_quality(P139)·operational_metrics(P167)·
hypothesis_discovery(P183). 새 원장 없음.
원칙(문서 §Constitution, §P196): 통합·조율만 · 결정적 · 자문 전용 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _ratio(n, d):
    return round(n / d, 4) if d else None


def build_research_metrics(*, topic: str = "") -> dict:
    """자율 연구 지표 7종(결정적·읽기전용). 값 없으면 정직하게 0/None."""
    summ = _safe(lambda: __import__("jarvis.research_ingestion.engine",
                                    fromlist=["ResearchIngestionEngine"]
                                    ).ResearchIngestionEngine().summary(), None)
    by = (getattr(summ, "by_outcome", None) or {}) if summ else {}
    total = int(getattr(summ, "ingestion_count", 0) or 0) if summ else 0
    kh = _safe(lambda: __import__("jarvis.research_workflow.knowledge_quality",
                                  fromlist=["build_knowledge_health"]).build_knowledge_health(), {}) or {}
    disc = _safe(lambda: __import__("jarvis.research_workflow.hypothesis_discovery",
                                    fromlist=["discover_research"]
                                    ).discover_research(topic, limit=8), {}) or {}

    success = int(by.get("SUCCESS", 0))
    failure = int(by.get("FAILURE", 0))
    incomplete = int(by.get("INCOMPLETE", 0))
    lessons = int(kh.get("total_lessons") or 0)

    metrics = {
        "generated_hypotheses": disc.get("hypothesis_count", 0),
        "accepted_research_proposals": 0,  # 사람 승인 데이터 없으면 0(정직)
        "completed_experiments": total,
        "validation_success_rate": _ratio(success, max(1, total - incomplete)),
        "avoided_duplicate_research": "idempotent_dedup_active",
        "knowledge_reuse_rate": _ratio(lessons, max(1, total)),
        "failure_prevention_count": failure,  # 검증에서 걸러진 실패 = 예방
    }
    return {"metrics": metrics,
            "measured_from": ["research_ingestion", "knowledge_quality", "hypothesis_discovery"],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Research Intelligence Metrics v3(읽기전용) — 자율 루프 7지표. 기존 원장 집계. "
                     "새 원장 없음. 사람이 해석·결정.")}
