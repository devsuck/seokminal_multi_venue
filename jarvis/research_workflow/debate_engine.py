"""Structured Debate Engine (P162) — 연구 결론에 도전한다. **읽기 전용, 예측 아님.**

**재사용**: Research Director·Critic(research_reviewer)·Research Writer·Knowledge Graph·Conflict Detection.
생성: Bull Case·Bear Case·Risk Case·Alternative Explanation·Missing Evidence·Historical Counterexamples.
출력: DebateReport. 목적: 연구 품질 개선(예측 아님). 새 저장소 없음.

원칙(문서 §Constitution, §P162): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_debate(question: str, *, spec: dict | None = None, metrics: dict | None = None,
                 assistant=None) -> dict:
    """연구 질문/스펙 → DebateReport(강세·약세·리스크·대안·누락·역사반례). 결정적·읽기전용."""
    q = (question or "").strip()

    # 비판(약세/리스크 근거) — ResearchReviewer(P126) 재사용
    review = _safe(lambda: __import__("jarvis.research_workflow.research_reviewer",
                                      fromlist=["review"]).review(spec or {"strategy_name": q},
                   metrics=metrics), {"critique": {"critiques": []}, "dimensions": {}})
    # 회수(강세 근거·과거) — semantic_recall(P133)
    recall = _safe(lambda: __import__("jarvis.research_workflow.semantic_recall", fromlist=["recall_context"])
                   .recall_context(q, assistant=assistant), {})
    # 모순/역사 반례 — conflict_detection(P135)
    conflicts = _safe(lambda: __import__("jarvis.research_workflow.conflict_detection",
                                         fromlist=["detect_conflicts"]).detect_conflicts(topic=q),
                      {"conflicts": []})

    crit = review.get("critique", {}).get("critiques", [])
    blocks = [c for c in crit if c.get("severity") == "BLOCK"]
    warns = [c for c in crit if c.get("severity") == "WARN"]

    bull = {"claim": f"{q} — 지지 근거",
            "evidence": recall.get("past_conclusions", [])[:4] or ["과거 결론 근거 축적 필요"],
            "prior_research": recall.get("prior_research_count", 0)}
    bear = {"claim": f"{q} — 반대 근거",
            "evidence": [c.get("finding") for c in blocks + warns][:5] or ["약세 근거 미검출 — 표본 확인"]}
    risk = {"main_risk": review.get("risk", {}).get("main_risk"),
            "label": review.get("risk", {}).get("main_risk_label"),
            "dimensions": review.get("dimensions", {})}
    alternative = {"explanation": _alt_explanation(review, conflicts),
                   "contradicting_evidence": recall.get("contradicting_evidence", [])[:3]}
    missing = (review.get("dimensions", {}).get("missing_evidence")
               or review.get("quality", {}).get("missing_validations") or [])
    counterexamples = [{"topic": c.get("topic"),
                        "study_a": c.get("study_a", {}).get("conclusion"),
                        "study_b": c.get("study_b", {}).get("conclusion"),
                        "explanation": c.get("possible_explanation")}
                       for c in conflicts.get("conflicts", [])[:5]]

    return {"question": q,
            "bull_case": bull, "bear_case": bear, "risk_case": risk,
            "alternative_explanation": alternative, "missing_evidence": missing,
            "historical_counterexamples": counterexamples,
            "debate_balance": {"bull_points": len(bull["evidence"]), "bear_points": len(bear["evidence"]),
                               "verdict_from_critic": review.get("verdict")},
            "report_type": "DebateReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("DebateReport(읽기전용) — 강세·약세·리스크·대안·누락·역사반례. 연구 품질 개선, 예측 아님. "
                     "director/critic/writer/knowledge_graph/conflict 재사용, 새 저장소 없음.")}


def _alt_explanation(review, conflicts) -> str:
    if conflicts.get("conflicts"):
        return conflicts["conflicts"][0].get("possible_explanation", "레짐/방법 차이 가능")
    dims = review.get("dimensions", {})
    if dims.get("overfitting_risk") in ("HIGH", "MEDIUM"):
        return "과적합/표본 특수성으로 인한 우연 결과 가능성"
    return "대체 설명 — 레짐 조건부/비용 가정 차이 확인 필요"
