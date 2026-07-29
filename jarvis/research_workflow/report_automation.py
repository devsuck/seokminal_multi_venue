"""Research Report Automation (P145) — ResearchWriter 를 확장한 자동 리포트. **요약·설명만, 결정 없음.**

생성: Daily Research Report·Weekly Research Letter·Strategy Review·Company Report. 표준 8섹션:
1.Research Question 2.Summary 3.Evidence 4.Historical Context 5.Risk 6.Contradictions 7.Conclusion
8.Next Research Step. **반드시 confidence·limitations 포함.** **재사용**: ResearchWriter(P127)·
semantic_recall(P133)·conflict_detection(P135). 새 저장소 없음.

원칙(문서 §Constitution, §P145): 통합·조율만. 결정적. 거래·집행·투자추천 없음. 사람 결정.
"""
from __future__ import annotations

REPORT_TYPES = ("daily_report", "weekly_letter", "strategy_review", "company_report")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


class ReportAutomation:
    """리포트 자동화 — ResearchWriter 확장(8섹션 표준). RESEARCH_ONLY. 투자 추천 없음."""

    def __init__(self, assistant=None) -> None:
        self._asst = assistant

    def generate(self, report_type: str, question: str, *, director=None, memos=None,
                 review=None) -> dict:
        """리포트 유형 + 질문 → 표준 8섹션 리포트(+confidence·limitations). 결정적·읽기전용."""
        rt = (report_type or "daily_report").lower()
        q = (question or "").strip()

        # ResearchWriter(P127, 7섹션) 재사용
        base = _safe(lambda: __import__("jarvis.research_workflow.research_writer",
                                        fromlist=["ResearchWriter"]).ResearchWriter(assistant=self._asst)
                     .write(q, director=director, memos=memos, review=review), {})
        wr = base.get("report", {})

        # 모순 — conflict_detection(P135)
        conflicts = _safe(lambda: __import__("jarvis.research_workflow.conflict_detection",
                                             fromlist=["detect_conflicts"]).detect_conflicts(topic=q),
                          {"conflicts": []})

        # 표준 8섹션(요약 + 모순 추가)
        sections = {
            "1_research_question": wr.get("1_research_question", q),
            "2_summary": self._summary(q, base, review),
            "3_evidence": wr.get("2_evidence", {}),
            "4_historical_context": wr.get("3_historical_context", {}),
            "5_risk": wr.get("5_risks", []),
            "6_contradictions": conflicts.get("conflicts", [])[:5],
            "7_conclusion": self._conclusion(base, review),
            "8_next_research_step": wr.get("7_next_research_step", []),
        }
        return {"report_type": rt, "report_format": "standard_8_section",
                "report": sections, "confidence": base.get("confidence", "LOW"),
                "limitations": base.get("limitations", ["자문이며 투자 결정이 아니다 — 사람 검토 필수."]),
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("자동 리포트(읽기전용) — 8섹션 표준 + confidence·limitations. 투자 추천 아님. "
                         "ResearchWriter/semantic_recall/conflict_detection 재사용, 새 저장소 없음.")}

    def _summary(self, q, base, review) -> str:
        conf = base.get("confidence", "LOW")
        verdict = (review or {}).get("verdict", "")
        return f"{q} — 신뢰도 {conf}" + (f", 리뷰 판정 {verdict}" if verdict else "") + " (자문, 결정 아님)."

    def _conclusion(self, base, review) -> str:
        verdict = (review or {}).get("verdict", "")
        if verdict == "BLOCK":
            return "현 근거로는 진행 부적합 — 추가 검증 필요(사람 검토)."
        if base.get("confidence") == "MEDIUM":
            return "부분적 근거 확보 — 다음 실험으로 확인 권장(사람 결정)."
        return "근거 축적 초기 — 추가 연구 필요(사람 결정)."


def generate(report_type: str, question: str, *, director=None, memos=None, review=None,
             assistant=None) -> dict:
    """모듈 진입점 — ReportAutomation.generate 래퍼."""
    return ReportAutomation(assistant=assistant).generate(report_type, question, director=director,
                                                          memos=memos, review=review)
