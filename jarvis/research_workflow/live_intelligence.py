"""Live Intelligence surface (P119) — Research OS → Live Intelligence 대시보드 백엔드. **읽기 전용.**

섹션: (1) Data Sources(provider 상태·coverage) (2) Market Feed(events·news·earnings)
(3) Research Queue(생성된 후보) (4) Data Health(API/data 품질). **재사용**: providers(P112)·
research_feed(P117)·data_quality(P118). 새 저장소 없음 — 모두 파생/조율.

원칙(문서 §Constitution, §P119): 통합·시각화만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

# 데이터 소스 미연결 시 피드/큐 시연용 결정적 데모(정직하게 is_demo 표기)
_DEMO_SOURCES = {
    "market": [{"asset": "AAPL", "return": 0.08, "timestamp": "2026-01-03T09:30:00Z", "source": "yfinance"}],
    "news": [{"text": "TSMC supplier expands production capacity", "entity": "TSMC"}],
    "ownership": [{"entity": "NVDA", "type": "BUY", "role": "CEO", "prior_return": -0.2,
                   "size": 2e6, "source": "SEC_FORM4", "actor": "CEO"}],
}


def build_live_intelligence(*, demo: bool = True) -> dict:
    """Live Intelligence 표면 조립(읽기전용) — data sources·market feed·research queue·data health."""
    from jarvis.research_workflow.providers import provider_registry
    reg = provider_registry()

    feed = {}
    if demo:
        from jarvis.research_workflow.research_feed import collect
        feed = _safe(lambda: collect(_DEMO_SOURCES), {}) or {}

    from jarvis.research_workflow.data_quality import build_data_health
    health = _safe(lambda: build_data_health(), {"overall_status": "LIMITED"}) or {}

    collected = feed.get("collected", [])
    market_feed = [{"category": c["category"],
                    "label": (c["event"].get("headline") or c["event"].get("asset")
                              or c["event"].get("company") or c["event"].get("event_type") or "event"),
                    "event_type": c["event"].get("event_type") or c["event"].get("transaction")
                    or c["event"].get("overall_surprise") or "",
                    "affected": (c["event"].get("affected_companies")
                                 or c["event"].get("related_entities") or [])[:4]}
                   for c in collected]

    return {"data_sources": {"providers": reg["providers"], "count": reg["count"],
                             "available_count": reg["available_count"],
                             "by_category": reg["by_category"]},
            "market_feed": market_feed,
            "research_queue": feed.get("opportunity_queue", []),
            "research_queue_count": feed.get("opportunity_count", 0),
            "dropped_duplicates": feed.get("dropped_duplicates", 0),
            "data_health": {"overall_status": health.get("overall_status"),
                            "api_availability": health.get("api_availability", {}),
                            "issue_count": health.get("issue_count", 0),
                            "checks": health.get("checks", [])},
            "is_demo": demo,
            "is_advisory": True, "is_decision": False,
            "disclaimer": ("Live Intelligence — READ ONLY. 외부데이터→provider→정규화→이벤트→연구큐. "
                           "데이터 소스 미연결 시 데모. 자동 거래·집행·자본배분 없음. 사람이 모든 결정.")}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default
