"""Research Report Agent (P127) — 연구 리포트를 작성한다. **요약·설명만, 결정/추천 없음.**

Structure(7 sections): 1.Research Question 2.Evidence 3.Historical Context 4.Analysis 5.Risks
6.Missing Evidence 7.Next Research Step. **반드시 confidence·limitations 포함.** **재사용**: recall(과거)·
decision_support(증거/신뢰도)·explainability. 새 지능/메모리 없음.

원칙(문서 §Constitution, §P127): 통합·조율만. 결정적. 거래·집행·투자추천 없음. 사람 결정.
"""
from __future__ import annotations


class ResearchWriter:
    """연구 작성자 — 디렉터 계획·전문가 메모·리뷰를 7섹션 Research Report 로 종합. RESEARCH_ONLY."""

    role = "report"
    level = "RESEARCH_ONLY"

    def __init__(self, assistant=None) -> None:
        self._asst = assistant

    def write(self, question: str, *, director=None, memos=None, review=None) -> dict:
        """연구 질문 + 계획/메모/리뷰 → Research Report(7섹션 + 신뢰도 + 한계). 결정적·읽기전용."""
        q = (question or "").strip()
        memos = memos or {}
        review = review or {}

        # 증거/신뢰도 — decision_support 재사용
        memo_obj = _safe(lambda: _decision_memo(self._asst, q), {})

        # 과거 — recall 재사용
        recall = _safe(lambda: _recall(self._asst, q), {})

        # 리스크/누락 — review 에서 파생
        risks = _collect_risks(review, memos)
        missing = (review.get("dimensions", {}).get("missing_evidence")
                   or review.get("quality", {}).get("missing_validations") or [])
        confidence = memo_obj.get("confidence") or _confidence(review, recall)

        sections = {
            "1_research_question": q,
            "2_evidence": {"digest": memo_obj.get("evidence", {}), "supporting":
                           memo_obj.get("supporting_arguments", []),
                           "specialist_memos": list(memos.keys())},
            "3_historical_context": {"recall": recall,
                                     "similar_cases": memo_obj.get("historical_similar_cases", [])},
            "4_analysis": {"market": _brief(memos.get("market")), "company": _brief(memos.get("company")),
                           "strategy": _brief(memos.get("strategy")),
                           "counter_arguments": memo_obj.get("counter_arguments", [])},
            "5_risks": risks,
            "6_missing_evidence": missing,
            "7_next_research_step": (memo_obj.get("suggested_next_research")
                                     or [(director or {}).get("hypothesis", "다음 실험 설계")]),
        }
        return {"report": sections, "confidence": confidence,
                "limitations": self._limitations(memos, review, recall),
                "verdict_from_review": review.get("verdict"),
                "report_type": "Research Report",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("Research Report(읽기전용) — 7섹션 + 신뢰도 + 한계. 투자 추천 아님. "
                         "recall/decision_support/explainability 재사용. 사람 결정.")}

    def _limitations(self, memos, review, recall) -> list:
        lims = ["분석은 자문(advisory)이며 투자 결정이 아니다 — 사람 검토 필수."]
        if not recall.get("prior_records"):
            lims.append("과거 유사 연구 기록이 적음 — 근거 축적 필요.")
        if review.get("dimensions", {}).get("validation_quality") == "WEAK":
            lims.append("검증 품질 미흡 — 추가 검증 전 신뢰 제한.")
        if not memos:
            lims.append("전문가 메모 부족 — 커버리지 제한.")
        return lims


def _decision_memo(assistant, q):
    from jarvis.research_workflow.decision_support import DecisionSupportEngine
    memo = DecisionSupportEngine(assistant=assistant).build_memo(q, topic=q)
    return memo.to_dict() if hasattr(memo, "to_dict") else dict(memo)


def _recall(assistant, q):
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    r = assistant.recall(q)
    return {"prior_records": r.total_hits, "tried_before": r.tried_before, "headline": r.headline}


def _collect_risks(review, memos) -> list:
    risks = []
    if review.get("risk", {}).get("main_risk"):
        risks.append({"source": "review", "risk": review["risk"]["main_risk"],
                      "label": review["risk"].get("main_risk_label")})
    for w in review.get("dimensions", {}).get("weak_assumptions", []) or []:
        risks.append({"source": "assumption", "risk": w})
    return risks or [{"source": "general", "risk": "표본/기간/레짐 확인 필요"}]


def _brief(memo) -> dict:
    if not isinstance(memo, dict):
        return {}
    return {k: memo[k] for k in ("memo_type", "market_condition", "fundamentals", "primary_hypothesis",
                                 "opportunities") if k in memo}


def _confidence(review, recall) -> str:
    if review.get("verdict") == "BLOCK":
        return "LOW"
    if review.get("verdict") == "PASS" and recall.get("prior_records", 0) >= 1:
        return "MEDIUM"
    return "LOW"


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def write(question: str, *, director=None, memos=None, review=None, assistant=None) -> dict:
    """모듈 진입점 — ResearchWriter.write 래퍼."""
    return ResearchWriter(assistant=assistant).write(question, director=director, memos=memos,
                                                     review=review)
