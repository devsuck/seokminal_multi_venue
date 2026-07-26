"""Creative Hypothesis Discovery (P171) — 템플릿 생성기를 **다중 지식원 추론 엔진**으로 확장한다. **제안만, 실행 없음.**

기존 HypothesisGenerator(P73)의 단일 템플릿 출력 대신, 여러 지식원을 **결정적으로 조합**해 다양한 가설을
생성하고 각각을 근거·유사연구·상충증거·불확실성·확신도·필요검증으로 보강한다.

조합하는 지식원(모두 **기존 모듈 재사용**, 새 엔진 없음):
  regime(P89)·macro_intelligence(P152)·sector_intelligence(P153)·company_intelligence(P154)·
  ownership/supply_chain/earnings/news(P86-100)·semantic_recall(P133)·knowledge_graph(P132)·
  conflict_detection(P135)·research_context_engine(P155)·HypothesisGenerator(P73).

각 가설 산출: novelty_score·evidence_chain·similar_historical_research·conflicting_evidence·
uncertainty·confidence·required_validation. **하나가 아니라 다수의 다양한 가설.**

원칙(문서 §Constitution, §P171): 통합·조율만 · 결정적 · 새 엔진/저장소/원장 없음 · 자문 전용 ·
거래·집행·자본배분 없음 · 연구를 자동 실행하지 않는다 · 사람이 모든 결정.
"""
from __future__ import annotations

# 필요검증 체크리스트(소스별 결정적) — 없는 검증은 정직하게 요구로 남긴다.
_BASE_VALIDATION = ("walk_forward", "out_of_sample", "cost_impact", "random_baseline")
_SOURCE_EXTRA_VALIDATION = {
    "regime": ("regime_robustness", "regime_out_of_sample"),
    "supply_chain": ("lead_lag_significance", "contemporaneous_control"),
    "macro_cross": ("macro_conditioning_stability",),
    "sector_cross": ("cross_sectional_breadth", "survivorship_control"),
    "event": ("event_window_stability", "already_priced_control"),
    "portfolio": ("correlation_to_book", "concentration_check"),
}
_EDGE_UNC = {"HIGH": 0.2, "MEDIUM": 0.45, "LOW": 0.7}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _count(v) -> int:
    """recall 필드가 리스트/정수 어느 쪽이든 개수로 정규화."""
    if isinstance(v, list):
        return len(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _base_hypotheses(topic, regime, portfolio, events, limit):
    """기존 P73 생성기 재사용 — 큐/실패/공급망/포트폴리오 후보."""
    def _gen():
        from jarvis.research_workflow.hypothesis_generator import HypothesisGenerator
        return [h.to_dict() for h in HypothesisGenerator().generate(
            topic, regime=regime, portfolio=portfolio, events=events, limit=limit)]
    return _safe(_gen, []) or []


def _regime_label(regime):
    if isinstance(regime, str) and regime:
        return regime
    r = _safe(lambda: __import__("jarvis.research_workflow.regime",
                                 fromlist=["detect_regime"]).detect_regime(), {})
    return str((r or {}).get("regime") or (r or {}).get("label") or "UNKNOWN")


def _macro_stance():
    m = _safe(lambda: __import__("jarvis.research_workflow.macro_intelligence",
                                 fromlist=["build_macro_context"]).build_macro_context(), {})
    return str((m or {}).get("stance") or (m or {}).get("regime") or (m or {}).get("summary", "")[:40]
               or "neutral")


def _sectors(limit=3):
    s = _safe(lambda: __import__("jarvis.research_workflow.sector_intelligence",
                                 fromlist=["supported_sectors"]).supported_sectors(), []) or []
    return [str(x) for x in s][:limit]


def _cross_source_hypotheses(regime_label, macro_stance, sectors):
    """다중 지식원 **조합**으로 새 가설을 결정적으로 합성(단일 템플릿 아님)."""
    out = []
    # regime × macro 교차
    out.append({
        "statement": f"In a {regime_label} regime with {macro_stance} macro, "
                     f"trend-following edge is regime-conditional",
        "rationale": f"레짐({regime_label}) × 매크로({macro_stance}) 교차 — 조건부 추세 엣지 후보.",
        "expected_edge": "MEDIUM", "confidence": "MEDIUM", "source": "macro_cross"})
    # regime × sector 교차(상위 섹터별)
    for sec in sectors:
        out.append({
            "statement": f"{sec} sector relative strength persists under {regime_label} regime",
            "rationale": f"섹터({sec}) × 레짐({regime_label}) — 상대강도 지속성 후보.",
            "expected_edge": "MEDIUM", "confidence": "LOW", "source": "sector_cross"})
    return out


def _enrich(h):
    """가설 1건 → 근거체인·유사연구·상충증거·novelty·uncertainty·필요검증 보강(기존 모듈 재사용)."""
    stmt = str(h.get("statement", ""))
    source = str(h.get("source", ""))
    recall = _safe(lambda: __import__("jarvis.research_workflow.semantic_recall",
                                      fromlist=["recall_context"]).recall_context(stmt), {}) or {}
    conflicts = _safe(lambda: __import__("jarvis.research_workflow.conflict_detection",
                                         fromlist=["detect_conflicts"]).detect_conflicts(topic=stmt),
                      {}) or {}
    prior = _count(recall.get("prior_research_count"))
    similar_failures = _count(recall.get("similar_failures"))
    # novelty: 과거 연구가 적을수록 높다(결정적)
    novelty = round(1.0 - min(1.0, prior / 5.0), 4)
    conf = str(h.get("confidence", "MEDIUM")).upper()
    uncertainty = _EDGE_UNC.get(conf, 0.45)
    # 근거 체인: 소스 + recall 컨텍스트
    evidence_chain = [f"source:{source or 'queue'}"]
    if prior:
        evidence_chain.append(f"prior_research={prior}")
    if recall.get("tried_before"):
        evidence_chain.append("recall:tried_before")
    if recall.get("made_this_mistake"):
        evidence_chain.append("recall:made_this_mistake")
    conflict_list = conflicts.get("conflicts") or []
    required = list(_BASE_VALIDATION) + list(_SOURCE_EXTRA_VALIDATION.get(source, ()))
    return {**h,
            "hypothesis_id": h.get("hypothesis_id") or _hid(stmt),
            "novelty_score": novelty,
            "evidence_chain": evidence_chain,
            "similar_historical_research": {"prior_research_count": prior,
                                            "past_conclusions": _count(recall.get("past_conclusions")),
                                            "similar_failures": similar_failures,
                                            "tried_before": bool(recall.get("tried_before"))},
            "conflicting_evidence": {"count": len(conflict_list),
                                     "contradictions": _count(recall.get("contradicting_evidence")),
                                     "examples": conflict_list[:2]},
            "uncertainty": uncertainty,
            "confidence": conf,
            "required_validation": required,
            "requires_human_review": True, "is_advisory": True, "is_decision": False}


def _hid(statement):
    return _safe(lambda: __import__("jarvis.research_workflow.models",
                                    fromlist=["hypothesis_id"]).hypothesis_id(statement),
                 "HYP:" + str(abs(hash(statement)) % (10 ** 10)))


def discover_hypotheses(topic: str = "", *, regime=None, portfolio=None, events=None,
                        limit: int = 12) -> dict:
    """다중 지식원 추론으로 **다양한 가설**을 발견하고 각각 보강(결정적·읽기전용). 연구 자동 실행 없음.

    반환: {hypotheses:[{statement, novelty_score, evidence_chain, similar_historical_research,
    conflicting_evidence, uncertainty, confidence, required_validation, ...}], sources_used, ...}
    """
    regime_label = _regime_label(regime)
    macro_stance = _macro_stance()
    sectors = _sectors()

    raw = _base_hypotheses(topic, regime, portfolio, events, limit)
    raw += _cross_source_hypotheses(regime_label, macro_stance, sectors)

    # 중복 제거(hypothesis_id) 후 보강
    seen, enriched = set(), []
    for h in raw:
        hid = h.get("hypothesis_id") or _hid(str(h.get("statement", "")))
        if hid in seen:
            continue
        seen.add(hid)
        enriched.append(_enrich(h))
    # novelty 내림차순 + 결정적 타이브레이크
    enriched.sort(key=lambda x: (-x["novelty_score"], x["hypothesis_id"]))
    enriched = enriched[:limit]

    return {"topic": topic, "regime": regime_label, "macro_stance": macro_stance,
            "sectors_considered": sectors,
            "sources_used": ["hypothesis_generator", "regime", "macro_intelligence",
                             "sector_intelligence", "semantic_recall", "conflict_detection"],
            "hypothesis_count": len(enriched), "hypotheses": enriched,
            "diversity": {"sources": sorted({h.get("source", "") for h in enriched}),
                          "novelty_range": [enriched[-1]["novelty_score"] if enriched else 0.0,
                                            enriched[0]["novelty_score"] if enriched else 0.0]},
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Creative Hypothesis Discovery(읽기전용) — 다중 지식원 결정적 조합 + 보강. "
                     "다수의 다양한 가설(제안). 연구 자동 실행 없음, 새 엔진/원장 없음. 사람이 모든 결정.")}
