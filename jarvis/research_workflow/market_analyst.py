"""Market Analyst Agent (P123) — 시장 상황을 요약하고 관련 이벤트·컨텍스트를 제공한다. **분석만.**

Uses: market_intelligence(market_cockpit)·event_stream·regime·opportunity_discovery·news_pipeline.
Tasks: 시장 상황 요약·관련 이벤트 식별·컨텍스트 제공. Output: Market Research Memo. 새 지능/메모리 없음.

원칙(문서 §Constitution, §P123): 통합·조율만. 결정적. 거래·집행·신호 없음. 사람 결정.
"""
from __future__ import annotations


class MarketAnalyst:
    """시장 분석가 — 레짐·이벤트·기회·컨텍스트를 요약한 Market Research Memo. RESEARCH_ONLY."""

    role = "specialist"
    level = "RESEARCH_ONLY"

    def __init__(self, assistant=None) -> None:
        self._asst = assistant

    def memo(self, *, topic: str = "", events=None, market: dict | None = None) -> dict:
        """시장 상황 → Market Research Memo(레짐·이벤트·기회·컨텍스트). 결정적·읽기전용."""
        # 1) 레짐 — regime 재사용
        regime = _safe(lambda: __import__("jarvis.research_workflow.regime",
                                          fromlist=["detect_regime"]).detect_regime(market or {}),
                       {"regime": "UNKNOWN"})
        # 2) 시장 콕핏(통합 시장 지능) — market_cockpit 재사용
        cockpit = _safe(lambda: __import__("jarvis.research_workflow.market_cockpit",
                                           fromlist=["build_market_cockpit"])
                        .build_market_cockpit(market or {}, {}), {})
        # 3) 관련 이벤트 — event_stream 재사용
        ev = _safe(lambda: __import__("jarvis.research_workflow.event_stream", fromlist=["stream"])
                   .stream(events or [], assistant=self._asst), {"research_events": [], "by_type": {}})
        # 4) 기회 — opportunity_discovery 재사용
        opps = _safe(lambda: __import__("jarvis.research_workflow.opportunity_discovery",
                                        fromlist=["discover"]).discover({}, assistant=self._asst),
                     {"opportunities": []})

        labels = regime.get("labels", []) if isinstance(regime, dict) else []
        return {"topic": topic, "market_condition": {"regime": regime.get("regime"),
                "labels": labels, "recommended_research": regime.get("recommended_research", []),
                "avoid": regime.get("avoid", [])},
                "relevant_events": ev.get("research_events", [])[:10],
                "events_by_type": ev.get("by_type", {}),
                "context": cockpit.get("market_state", cockpit) if isinstance(cockpit, dict) else {},
                "opportunities": opps.get("opportunities", [])[:5],
                "memo_type": "Market Research Memo",
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "is_trade_signal": False,
                "note": ("Market Research Memo(읽기전용) — 레짐·이벤트·기회·컨텍스트. 신호 아님. "
                         "market_intelligence/event_stream/regime 재사용, 새 메모리 없음.")}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def memo(*, topic: str = "", events=None, market: dict | None = None, assistant=None) -> dict:
    """모듈 진입점 — MarketAnalyst.memo 래퍼."""
    return MarketAnalyst(assistant=assistant).memo(topic=topic, events=events, market=market)
