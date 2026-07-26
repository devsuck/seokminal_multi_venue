"""Research Conviction Framework (P163) — 연구에 대한 확신도를 측정한다. **투자 등급 아님.**

요인: Evidence Quality·Historical Similarity·Knowledge Consistency·Risk Level·Uncertainty·Validation Quality.
출력: ResearchConvictionReport(LOW/MEDIUM/HIGH). **투자 등급으로 해석 금지** — 연구 확신도일 뿐.
**재사용**: intelligence_quality(P158)·semantic_recall(P133)·quality_monitor(P106)·conflict_detection(P135).

원칙(문서 §Constitution, §P163): 통합·조율만. 결정적. 거래·집행·등급 없음. 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _clip(x):
    return round(max(0.0, min(1.0, x)), 3)


def build_conviction(topic: str, *, spec: dict | None = None, metrics: dict | None = None,
                     assistant=None) -> dict:
    """토픽 → ResearchConvictionReport(6요인 + LOW/MEDIUM/HIGH). 투자 등급 아님. 결정적·읽기전용."""
    t = (topic or "").strip()

    # 정보 품질(data/evidence/historical/conflict/uncertainty) — intelligence_quality
    iq = _safe(lambda: __import__("jarvis.research_workflow.intelligence_quality",
                                  fromlist=["score_intelligence"]).score_intelligence(topic=t,
               assistant=assistant), {"dimensions": {}})
    dims = iq.get("dimensions", {})
    # 검증 품질 — quality_monitor
    quality = _safe(lambda: __import__("jarvis.research_workflow.quality_monitor", fromlist=["evaluate"])
                    .evaluate({"strategy_name": t, "metrics": metrics or {}}, assistant=assistant),
                    {"quality_score": 0})
    # 지식 일관성 — conflict_detection(모순 적을수록 일관)
    conflicts = _safe(lambda: __import__("jarvis.research_workflow.conflict_detection",
                                         fromlist=["detect_conflicts"]).detect_conflicts(topic=t),
                      {"count": 0})

    factors = {
        "evidence_quality": _clip(dims.get("evidence_quality", 0.0)),
        "historical_similarity": _clip(dims.get("historical_relevance", 0.0)),
        "knowledge_consistency": _clip(1.0 - min(conflicts.get("count", 0) / 3.0, 1.0)),
        "risk_level": _clip(1.0 - dims.get("conflict_level", 0.0)),        # 낮은 리스크=높은 점수
        "uncertainty": _clip(1.0 - dims.get("uncertainty", 0.0)),          # 낮은 불확실성=높은 점수
        "validation_quality": _clip(float(quality.get("quality_score", 0) or 0) / 100.0),
    }
    score = round(sum(factors.values()) / len(factors), 3)
    level = "HIGH" if score >= 0.65 else "MEDIUM" if score >= 0.4 else "LOW"
    return {"topic": t, "factors": factors, "conviction_score": score, "conviction_level": level,
            "rationale": (f"evidence={factors['evidence_quality']}, historical={factors['historical_similarity']}, "
                          f"consistency={factors['knowledge_consistency']}, validation={factors['validation_quality']}"),
            "disclaimer": "연구 확신도 — 투자 등급/추천이 아니다. 사람이 모든 투자 판단.",
            "report_type": "ResearchConvictionReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "is_investment_rating": False,
            "note": ("ResearchConvictionReport(읽기전용) — 6요인 → LOW/MEDIUM/HIGH. 투자 등급 아님. "
                     "intelligence_quality/recall/quality_monitor/conflict 재사용, 새 저장소 없음.")}
