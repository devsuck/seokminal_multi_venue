"""Company Analyst Agent (P124) — 재무·실적·비즈니스 이벤트·경쟁지위를 분석한다. **분석만.**

Uses: fundamental_pipeline·earnings_intelligence·news_pipeline·insider_flow. Output: Company Research Memo.
재무 변화·실적·비즈니스 이벤트·경쟁 지위 분석. 새 지능/메모리 없음 — 기존 파이프라인/어댑터 재사용.

원칙(문서 §Constitution, §P124): 통합·조율만. 결정적. 거래·집행·신호 없음. 사람 결정.
"""
from __future__ import annotations


class CompanyAnalyst:
    """기업 분석가 — 재무·실적·이벤트·경쟁지위를 요약한 Company Research Memo. RESEARCH_ONLY."""

    role = "specialist"
    level = "RESEARCH_ONLY"

    def __init__(self, assistant=None) -> None:
        self._asst = assistant

    def memo(self, company: str, *, financials=None, headlines=None, transactions=None) -> dict:
        """기업 → Company Research Memo(재무·실적·이벤트·경쟁·내부자). 결정적·읽기전용."""
        name = (company or "").strip()

        # 1) 재무/실적 — fundamental_pipeline 재사용
        fundamentals = _safe(lambda: __import__("jarvis.research_workflow.fundamental_pipeline",
                                                fromlist=["run"]).run(financials or [],
                             assistant=self._asst), {"research_candidates": []})
        # 2) 비즈니스 이벤트(뉴스) — news_pipeline 재사용
        news = _safe(lambda: __import__("jarvis.research_workflow.news_pipeline", fromlist=["run"])
                     .run(headlines or [], assistant=self._asst), {"research_context": []})
        # 3) 내부자/소유 — insider_flow 재사용
        insider = _safe(lambda: __import__("jarvis.research_workflow.insider_flow", fromlist=["stream"])
                        .stream(transactions or [], assistant=self._asst), {"events": []})
        # 4) 과거 유사 — recall 재사용
        recall = {}
        if name:
            recall = _safe(lambda: _recall(self._asst, name), {})

        candidates = fundamentals.get("research_candidates", [])
        competitive = [c for c in news.get("research_context", []) if c.get("sector")]
        return {"company": name or "unknown",
                "fundamentals": candidates,
                "earnings": [{"company": c["company"], "period": c.get("period"),
                              "surprise": c.get("overall_surprise")} for c in candidates],
                "business_events": news.get("research_context", [])[:8],
                "competitive_position": competitive[:5],
                "insider_activity": insider.get("events", [])[:5],
                "historical_context": recall,
                "memo_type": "Company Research Memo",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "is_trade_signal": False,
                "note": ("Company Research Memo(읽기전용) — 재무·실적·이벤트·경쟁·내부자. 신호 아님. "
                         "fundamental/earnings/news/insider 재사용, 새 메모리 없음.")}


def _recall(assistant, name):
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    r = assistant.recall(name)
    return {"prior_records": r.total_hits, "tried_before": r.tried_before, "headline": r.headline}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def memo(company: str, *, financials=None, headlines=None, transactions=None, assistant=None) -> dict:
    """모듈 진입점 — CompanyAnalyst.memo 래퍼."""
    return CompanyAnalyst(assistant=assistant).memo(company, financials=financials,
                                                    headlines=headlines, transactions=transactions)
