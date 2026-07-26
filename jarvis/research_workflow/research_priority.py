"""Research Priority Engine (P185) — 수많은 연구 후보 중 우선순위를 결정한다. **추천만, 결정 없음.**

Research Priority Score =
  Novelty + Evidence Quality + Data Availability + Expected Information Gain
  + Knowledge Gap Reduction − Complexity − Duplicate Risk.

**재사용**: experiment_prioritization(P174, 커버리지·갭)·experiment_designer(P184, info gain·complexity)·
semantic_recall(P133, duplicate risk). 각 순위 항목에 '왜 중요한지' 설명 첨부.

원칙(문서 §Constitution, §P185): 통합·조율만 · 결정적 · 추천만 · 자문 전용 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

# 점수 가중(결정적) — 양의 요인 + / 음의 요인 −
_W = {"novelty": 0.22, "evidence_quality": 0.16, "data_availability": 0.12,
      "expected_information_gain": 0.20, "knowledge_gap_reduction": 0.14,
      "complexity": 0.12, "duplicate_risk": 0.14}


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


def _coverage():
    ctx = _safe(lambda: __import__("jarvis.research_workflow.experiment_prioritization",
                                   fromlist=["prioritize_experiments"]
                                   ).prioritize_experiments(candidates=[], limit=1
                                                            ).get("coverage_context", {}), {}) or {}
    return float(ctx.get("research_coverage") or 0.0), float(ctx.get("knowledge_gap") or 0.0)


def _factors(cand, coverage, knowledge_gap):
    """후보 dict → 7요인(결정적, 0~1)."""
    novelty = float(cand.get("novelty", cand.get("novelty_score", 0.5)))
    # 근거 품질 = supporting_evidence 수 대비
    ev = cand.get("supporting_evidence") or cand.get("evidence_chain") or []
    evidence_quality = round(min(1.0, len(ev) / 4.0), 4)
    # 데이터 가용성 = required_test/데이터 명시 여부
    req = cand.get("required_test") or cand.get("required_validation") or []
    data_availability = round(0.4 + 0.1 * min(6, len(req)), 4) if req else 0.4
    info_gain = float(cand.get("information_gain_score", round(0.6 * novelty + 0.4 * evidence_quality, 4)))
    gap_reduction = round(knowledge_gap * novelty, 4)
    complexity = float(cand.get("complexity_score", round(min(1.0, len(req) / 6.0), 4)))
    # 중복 위험 = 과거 유사 연구/실패
    prior = _count((cand.get("similar_research") or {}).get("prior_research_count")) \
        if isinstance(cand.get("similar_research"), dict) else _count(cand.get("prior_research_count"))
    dup_risk = round(min(1.0, prior / 5.0), 4)
    return {"novelty": novelty, "evidence_quality": evidence_quality,
            "data_availability": data_availability, "expected_information_gain": info_gain,
            "knowledge_gap_reduction": gap_reduction, "complexity": complexity,
            "duplicate_risk": dup_risk}


def _score(f):
    return round(_W["novelty"] * f["novelty"] + _W["evidence_quality"] * f["evidence_quality"]
                 + _W["data_availability"] * f["data_availability"]
                 + _W["expected_information_gain"] * f["expected_information_gain"]
                 + _W["knowledge_gap_reduction"] * f["knowledge_gap_reduction"]
                 - _W["complexity"] * f["complexity"] - _W["duplicate_risk"] * f["duplicate_risk"], 4)


def _why(f):
    reasons = []
    if f["novelty"] >= 0.7:
        reasons.append("높은 신규성(선행연구 적음)")
    if f["knowledge_gap_reduction"] >= 0.3:
        reasons.append("지식 갭 축소 기여")
    if f["expected_information_gain"] >= 0.6:
        reasons.append("기대 정보 획득 큼")
    if f["duplicate_risk"] >= 0.6:
        reasons.append("중복 위험 높음(감점)")
    if f["complexity"] >= 0.6:
        reasons.append("복잡도 높음(감점)")
    return " · ".join(reasons) or "요인 균형 — 중위 우선순위"


def prioritize_research(candidates, *, limit: int = 10) -> dict:
    """연구 후보 → Research Priority Score 순위 큐(각 항목 '왜 중요한지' 설명). 결정적·읽기전용."""
    coverage, knowledge_gap = _coverage()
    cands = [c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in (candidates or [])]
    scored = []
    for c in cands:
        f = _factors(c, coverage, knowledge_gap)
        scored.append({"hypothesis_id": c.get("hypothesis_id", ""),
                       "question": c.get("question") or c.get("statement", ""),
                       "priority_score": _score(f), "factors": f, "why_important": _why(f)})
    scored.sort(key=lambda x: (-x["priority_score"], x["hypothesis_id"]))
    for i, s in enumerate(scored, 1):
        s["rank"] = i
    ranked = scored[:limit]
    return {"count": len(ranked),
            "coverage_context": {"research_coverage": coverage, "knowledge_gap": knowledge_gap},
            "formula": "novelty+evidence+data+info_gain+gap_reduction-complexity-duplicate_risk",
            "research_queue": ranked, "top": ranked[0] if ranked else {},
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Research Priority Engine(읽기전용) — 7요인 결정적 스코어, 각 항목 근거 첨부. "
                     "추천만, 새 저장소 없음. 사람이 무엇을 검토할지 결정.")}
