"""Intelligence Quality Scoring (P158) — 정보 신뢰도를 측정한다. **읽기 전용, 결정적.**

점수: Data quality·Evidence quality·Historical relevance·Conflict level·Uncertainty. 예: 고신뢰 = 다중 소스 +
역사적 뒷받침; 저신뢰 = 단일 소스 + 상충 증거. **재사용**: data_production(P151)·semantic_recall(P133)·
conflict_detection(P135)·knowledge_quality(P139). 출력: IntelligenceQualityReport. 새 저장소 없음.

원칙(문서 §Constitution, §P158): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _clip(x):
    return round(max(0.0, min(1.0, x)), 3)


def score_intelligence(*, topic: str = "", n_sources: int | None = None, assistant=None) -> dict:
    """정보 신뢰도 5차원 점수 + 종합 confidence(결정적·읽기전용).

    topic 있으면 recall/conflict 로 근거·모순 자동 측정. n_sources 로 데이터 소스 수 주입 가능.
    """
    t = (topic or "").strip()

    # 1) Data quality — data_production 평균 품질 + 가용성
    dp = _safe(lambda: __import__("jarvis.research_workflow.data_production",
                                  fromlist=["build_data_production"]).build_data_production(), {})
    data_quality = _clip(dp.get("average_quality", 0.5) if dp else 0.5)
    sources_available = dp.get("available_count", 0) if dp else 0
    n_src = n_sources if n_sources is not None else sources_available

    # 2) Evidence quality — recall 히트/과거 결론
    recall = _safe(lambda: __import__("jarvis.research_workflow.semantic_recall", fromlist=["recall_context"])
                   .recall_context(t or "market", assistant=assistant), {})
    prior = int(recall.get("prior_research_count", 0) or 0)
    evidence_quality = _clip(prior / 5.0)

    # 3) Historical relevance — 과거 유사 존재
    historical_relevance = _clip((1.0 if recall.get("tried_before") else 0.3) +
                                 (0.2 if recall.get("past_conclusions") else 0.0))

    # 4) Conflict level — conflict_detection(높을수록 신뢰 감점)
    conflicts = _safe(lambda: __import__("jarvis.research_workflow.conflict_detection",
                                         fromlist=["detect_conflicts"]).detect_conflicts(topic=t),
                      {"count": 0})
    n_conf = conflicts.get("count", 0)
    contradicting = len(recall.get("contradicting_evidence", []))
    conflict_level = _clip((n_conf + contradicting) / 5.0)

    # 5) Uncertainty — 소스 적고 모순 많으면 높음
    uncertainty = _clip((1.0 if n_src <= 1 else 0.5 if n_src <= 3 else 0.2) + conflict_level * 0.3)

    # 종합 confidence(결정적) — 다중소스+역사뒷받침 → HIGH; 단일소스+모순 → LOW
    reliability = round((data_quality + evidence_quality + historical_relevance) / 3
                        - conflict_level * 0.3 - uncertainty * 0.2, 3)
    confidence = ("HIGH" if (reliability >= 0.55 and n_src >= 2 and conflict_level < 0.3)
                  else "LOW" if (n_src <= 1 or conflict_level >= 0.5) else "MEDIUM")

    return {"topic": t, "dimensions": {
                "data_quality": data_quality, "evidence_quality": evidence_quality,
                "historical_relevance": historical_relevance, "conflict_level": conflict_level,
                "uncertainty": uncertainty},
            "n_sources": n_src, "reliability_score": _clip(reliability), "confidence": confidence,
            "rationale": (f"sources={n_src}, prior_research={prior}, conflicts={n_conf + contradicting}"),
            "report_type": "IntelligenceQualityReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("IntelligenceQualityReport(읽기전용) — data/evidence/historical/conflict/uncertainty. "
                     "고신뢰=다중소스+역사, 저신뢰=단일소스+모순. 재사용, 새 저장소 없음.")}
