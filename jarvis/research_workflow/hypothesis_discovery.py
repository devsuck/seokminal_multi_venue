"""Creative Hypothesis Generator v2 (P183) — 과거연구·실패·시장변화·지식그래프 기반 새 연구 질문. **제안만, 실행 없음.**

기존 creative_hypothesis(P171)를 확장한다. **생성 전 반드시**: ① semantic_recall 실행 ② 유사 연구 검색
③ 실패 연구 확인. 과거 실패와 유사하면 **"왜 이번에는 다른지"** 설명 필수.

출력 Research Hypothesis:
  question · why_now · novelty · supporting_evidence · contradicting_evidence · similar_research ·
  past_failures · required_test · unknowns · confidence.

**재사용**: creative_hypothesis(P171)·semantic_recall(P133)·market_observation(P182)·conflict_detection(P135).
원칙(문서 §Constitution, §P183): 통합·조율만 · 결정적 · 자문 전용 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

_CONF = {"HIGH": 0.75, "MEDIUM": 0.5, "LOW": 0.3}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _count(v) -> int:
    if isinstance(v, list):
        return len(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _recall(question):
    """생성 전 필수 — semantic_recall 로 과거연구·실패·유사연구 확인."""
    return _safe(lambda: __import__("jarvis.research_workflow.semantic_recall",
                                    fromlist=["recall_context"]).recall_context(question), {}) or {}


def _why_now(opportunity):
    if opportunity and opportunity.get("observation"):
        return f"시장 관찰: {opportunity['observation']} (type={opportunity.get('type')})"
    return "축적된 지식 갭 + 미해결 연구 질문에서 도출"


def _why_different(recall):
    """과거 실패와 유사할 때 '왜 이번엔 다른지' 설명(결정적). 정직: 근거 없으면 명시."""
    failures = _count(recall.get("similar_failures"))
    if failures <= 0:
        return ""
    diffs = []
    if recall.get("made_this_mistake"):
        diffs.append("과거 실패 원인을 교정 조건으로 사전 등록(walk-forward·비용·랜덤 베이스라인 강화)")
    diffs.append("레짐/유니버스/기간을 달리해 동일 아티팩트 반복 회피")
    diffs.append("과거 실패 대비 무엇이 바뀌었는지 입증 못 하면 재검증 보류(억지 결론 금지)")
    return " · ".join(diffs)


def _to_research_hypothesis(h, opportunity):
    """creative_hypothesis 출력 + recall → Research Hypothesis(v2 스키마)."""
    question = str(h.get("statement", ""))
    recall = _recall(question)
    sim = h.get("similar_historical_research", {}) or {}
    past_failures = _count(recall.get("similar_failures")) or sim.get("similar_failures", 0)
    conf = str(h.get("confidence", "MEDIUM")).upper()
    unknowns = list(h.get("required_validation", []))[:3] or ["엣지 지속성", "비용 후 생존", "레짐 강건성"]
    rh = {"hypothesis_id": h.get("hypothesis_id"),
          "question": question,
          "why_now": _why_now(opportunity),
          "novelty": h.get("novelty_score", 0.5),
          "supporting_evidence": h.get("evidence_chain", []),
          "contradicting_evidence": {"count": (h.get("conflicting_evidence", {}) or {}).get("count", 0),
                                     "contradictions": (h.get("conflicting_evidence", {}) or {}).get("contradictions", 0)},
          "similar_research": {"prior_research_count": sim.get("prior_research_count", 0),
                               "tried_before": sim.get("tried_before", False)},
          "past_failures": past_failures,
          "required_test": list(h.get("required_validation", [])),
          "unknowns": unknowns,
          "confidence": round(_CONF.get(conf, 0.5) * (0.6 + 0.4 * float(h.get("novelty_score", 0.5))), 4),
          "requires_human_review": True, "is_advisory": True, "is_decision": False}
    # 과거 실패와 유사하면 '왜 이번엔 다른지' 필수
    if past_failures > 0 or recall.get("tried_before"):
        rh["why_different_this_time"] = _why_different(recall) or "차별점 미입증 — 재검증 보류 권고"
    return rh


def discover_research(topic: str = "", *, opportunity: dict | None = None, limit: int = 8) -> dict:
    """새 연구 질문 발견(recall-first). 과거 실패 유사 시 '왜 다른지' 필수. 결정적·읽기전용.

    opportunity(선택): market_observation 의 Research Opportunity — why_now 근거.
    """
    seed = topic or (opportunity or {}).get("observation", "") or ""
    creative = _safe(lambda: __import__("jarvis.research_workflow.creative_hypothesis",
                                        fromlist=["discover_hypotheses"]
                                        ).discover_hypotheses(seed, limit=limit), {}) or {}
    hyps = creative.get("hypotheses", [])

    research = [_to_research_hypothesis(h, opportunity) for h in hyps]
    research.sort(key=lambda x: (-x["novelty"], x["hypothesis_id"]))
    research = research[:limit]

    with_diff = sum(1 for r in research if "why_different_this_time" in r)
    return {"topic": seed, "opportunity_id": (opportunity or {}).get("opportunity_id"),
            "hypothesis_count": len(research),
            "recall_first": True, "with_why_different": with_diff,
            "research_hypotheses": research,
            "sources": ["creative_hypothesis", "semantic_recall", "market_observation"],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Creative Hypothesis Generator v2(읽기전용) — recall-first, 과거 실패 유사 시 "
                     "'왜 이번엔 다른지' 필수. 제안만, 연구 자동 실행 없음, 새 저장소 없음. 사람이 결정.")}
