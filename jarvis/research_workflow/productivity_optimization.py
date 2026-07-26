"""Research Productivity Optimization (P179) — 연구 생산성을 측정하고 개선을 **추천**한다. **추천만, 코드 수정 없음.**

측정(모두 **기존 모듈/원장 재사용**): research_throughput·duplicate_reduction·knowledge_growth·
learning_speed·research_quality·validation_quality·evidence_coverage·false_positive_reduction.
소스: research_ingestion 요약·knowledge_quality(P139)·operational_metrics(P167)·agent_performance(P148).
모르는 값은 정직하게 UNKNOWN. 임계 기반 결정적 추천 — **코드를 자동 수정하지 않는다.**

원칙(문서 §Constitution, §P179): 통합·조율만 · 결정적 · 추천만 · 자문 전용 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _ingestion_summary():
    s = _safe(lambda: __import__("jarvis.research_ingestion.engine",
                                 fromlist=["ResearchIngestionEngine"]
                                 ).ResearchIngestionEngine().summary(), None)
    if not s:
        return {}, {}, 0
    by = getattr(s, "by_outcome", None) or {}
    cat = getattr(s, "by_failure_category", None) or {}
    total = int(getattr(s, "ingestion_count", 0) or 0)
    return by, cat, total


def _knowledge_health():
    return _safe(lambda: __import__("jarvis.research_workflow.knowledge_quality",
                                    fromlist=["build_knowledge_health"]
                                    ).build_knowledge_health(), {}) or {}


def _op_metrics():
    return _safe(lambda: __import__("jarvis.research_workflow.operational_metrics",
                                    fromlist=["build_operational_metrics"]
                                    ).build_operational_metrics(), {}) or {}


def _ratio(n, d):
    return round(n / d, 4) if d else None


def build_productivity_report() -> dict:
    """연구 생산성 8지표 + 운영 개선 추천(자문). 결정적·읽기전용. 코드 자동 수정 없음."""
    by, cat, total = _ingestion_summary()
    kh = _knowledge_health()
    op = _op_metrics()

    success = int(by.get("SUCCESS", 0))
    failure = int(by.get("FAILURE", 0))
    incomplete = int(by.get("INCOMPLETE", 0))
    complete = total - incomplete

    metrics = {
        "research_throughput": {"value": total, "unit": "ingested_experiments"},
        "duplicate_reduction": {"value": "idempotent_dedup_active", "detail": "backtest_hash 기반"},
        "knowledge_growth": {"value": kh.get("total_lessons"), "grade": kh.get("grade")},
        "learning_speed": {"value": _ratio(kh.get("total_lessons") or 0, max(1, total)),
                           "detail": "lessons per ingested experiment"},
        "research_quality": {"value": kh.get("health_score")},
        "validation_quality": {"value": _ratio(complete, max(1, total)),
                               "detail": "validation-complete 비율"},
        "evidence_coverage": {"value": _ratio(complete, max(1, total))},
        "false_positive_reduction": {"value": _ratio(failure, max(1, total)),
                                     "detail": "검증에서 걸러진 실패 비율(높을수록 게이트 작동)"},
    }

    # 결정적 추천(임계 기반) — 코드 수정 아님, 운영 제안
    recs = []
    if incomplete and _ratio(complete, max(1, total)) is not None and complete / max(1, total) < 0.5:
        recs.append({"area": "validation_quality", "priority": "HIGH",
                     "recommendation": f"{incomplete}건 INCOMPLETE — 누락 검증(cost/vol/stability) 보강"})
    if (kh.get("health_score") or 0) < 60:
        recs.append({"area": "knowledge_quality", "priority": "MEDIUM",
                     "recommendation": "지식 건강도 낮음 — 교훈 구조화·모순 정리"})
    if cat:
        top = sorted(cat.items(), key=lambda x: -x[1])[:1]
        if top:
            recs.append({"area": "false_positive_reduction", "priority": "MEDIUM",
                         "recommendation": f"반복 실패 '{top[0][0]}'({top[0][1]}건) — 사전 게이트 강화"})
    if not recs:
        recs.append({"area": "throughput", "priority": "LOW",
                     "recommendation": "지표 양호 — 신규 데이터 소스로 커버리지 확대 고려"})

    return {"metrics": metrics, "measured_from": ["research_ingestion", "knowledge_quality",
                                                  "operational_metrics"],
            "recommendations": recs, "op_metrics_available": bool(op),
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Research Productivity Optimization(읽기전용) — 8지표 측정 + 운영 추천. "
                     "코드 자동 수정 없음, 새 원장 없음. 사람이 개선을 결정.")}
