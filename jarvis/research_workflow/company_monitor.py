"""Company Monitoring System (P143) — 연구 대상 기업을 지속 추적한다. **읽기 전용, 매수/매도 신호 없음.**

Uses: fundamental_pipeline·earnings_intelligence·news_pipeline·ownership_pipeline(= CompanyAnalyst 재사용).
모니터: 재무변화·실적이벤트·뉴스이벤트·소유변화·산업이벤트. 출력: CompanyUpdateReport
{company, events, impact, historical_context, research_priority}. 새 저장소 없음.

원칙(문서 §Constitution, §P143): 통합·조율만. 결정적. 거래·집행·신호 없음. 사람 결정.
"""
from __future__ import annotations


class CompanyMonitor:
    """기업 모니터 — 재무·실적·뉴스·소유 변화를 추적한 CompanyUpdateReport. RESEARCH_ONLY. 신호 아님."""

    def __init__(self, assistant=None) -> None:
        self._asst = assistant

    def update(self, company: str, *, financials=None, headlines=None, transactions=None) -> dict:
        """기업 → CompanyUpdateReport(이벤트·영향·과거·연구우선순위). 결정적·읽기전용."""
        name = (company or "").strip()
        # CompanyAnalyst 재사용(재무·실적·뉴스·내부자)
        memo = _safe(lambda: __import__("jarvis.research_workflow.company_analyst",
                                        fromlist=["CompanyAnalyst"]).CompanyAnalyst(assistant=self._asst)
                     .memo(name, financials=financials, headlines=headlines, transactions=transactions),
                     {})

        events = []
        for c in memo.get("earnings", []):
            events.append({"kind": "earnings", "label": f"{c.get('company')} {c.get('period', '')}",
                           "detail": c.get("surprise")})
        for e in memo.get("business_events", []):
            events.append({"kind": "news", "label": e.get("headline", ""), "detail": e.get("event_type")})
        for i in memo.get("insider_activity", []):
            events.append({"kind": "ownership", "label": i.get("entity", name),
                           "detail": i.get("transaction_type")})

        impact = self._impact(memo)
        priority = self._priority(events, impact, memo)
        return {"company": name or "unknown", "events": events, "impact": impact,
                "historical_context": memo.get("historical_context", {}),
                "research_priority": priority,
                "competitive_position": memo.get("competitive_position", []),
                "report_type": "CompanyUpdateReport",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "is_trade_signal": False,
                "note": ("CompanyUpdateReport(읽기전용) — 재무·실적·뉴스·소유 변화. 매수/매도 신호 아님. "
                         "fundamental/earnings/news/ownership 재사용, 새 저장소 없음.")}

    def _impact(self, memo) -> dict:
        earnings = memo.get("earnings", [])
        pos = sum(1 for c in earnings if c.get("surprise") == "POSITIVE_SURPRISE")
        neg = sum(1 for c in earnings if c.get("surprise") == "NEGATIVE_SURPRISE")
        direction = "POSITIVE" if pos > neg else "NEGATIVE" if neg > pos else "NEUTRAL"
        return {"direction": direction, "positive_surprises": pos, "negative_surprises": neg,
                "news_events": len(memo.get("business_events", [])),
                "insider_events": len(memo.get("insider_activity", []))}

    def _priority(self, events, impact, memo) -> str:
        score = len(events) + (2 if impact["direction"] != "NEUTRAL" else 0) + \
            (1 if memo.get("insider_activity") else 0)
        return "HIGH" if score >= 4 else "MEDIUM" if score >= 1 else "LOW"


def update(company: str, *, financials=None, headlines=None, transactions=None, assistant=None) -> dict:
    """모듈 진입점 — CompanyMonitor.update 래퍼."""
    return CompanyMonitor(assistant=assistant).update(company, financials=financials,
                                                      headlines=headlines, transactions=transactions)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default
