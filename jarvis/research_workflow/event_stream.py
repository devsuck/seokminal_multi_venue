"""Real-Time Research Event Stream (P86) — 들어오는 정보를 **연구 이벤트**로 변환한다. **읽기 전용, 새 DB 없음.**

Data Event → 분류 → 영향 자산/섹터 탐지 → 과거 회상 → 연구 컨텍스트 → 사람 검토 큐.
**재사용**: event_intelligence(개체 전파/관계 그래프), research_assistant.recall(과거 회상), knowledge graph.
두 번째 이벤트 데이터베이스를 만들지 않는다 — 이벤트는 흘러가서 사람 검토 큐 오브젝트가 된다.

원칙(문서 §Constitution, §P86): 통합·조율만. 결정적. 거래·집행·신호 없음 — 연구 컨텍스트일 뿐.
"""
from __future__ import annotations

# data event kind → 연구 이벤트 분류(결정적)
_EVENT_TYPES = {
    "news": "NEWS", "earnings": "EARNINGS", "insider": "INSIDER", "macro": "MACRO",
    "economic": "ECONOMIC_CALENDAR", "supply": "SUPPLY_CHAIN", "market": "MARKET_DATA",
    "price": "MARKET_DATA", "sentiment": "SENTIMENT",
}


def _classify(event: dict) -> str:
    text = " ".join(str(v) for v in event.values()).lower()
    for kw, typ in _EVENT_TYPES.items():
        if kw in str(event.get("kind", "")).lower() or kw in text:
            return typ
    return "GENERAL"


def classify_event(event: dict, *, assistant=None) -> dict:
    """단일 data event → 연구 이벤트(분류·영향개체·회상·연구컨텍스트·검토큐). 결정적·읽기전용."""
    ev = event or {}
    etype = _classify(ev)
    origin = str(ev.get("entity") or ev.get("origin") or ev.get("symbol") or "").strip()
    label = str(ev.get("text") or ev.get("title") or ev.get("headline") or ev.get("kind") or "event")

    # 영향 자산/섹터 — event_intelligence 재사용(공급망/관계 전파)
    affected, chain = [], {"nodes": [], "edges": []}
    try:
        from jarvis.research_assistant.event_intelligence import MarketEventIntelligence
        imp = MarketEventIntelligence().analyze_event(ev if origin else {"text": label})
        affected = imp.affected_entities
        chain = imp.impact_chain
        origin = origin or imp.origin
    except Exception:  # noqa: BLE001
        pass

    # 과거 회상 — recall 재사용
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    recall_topic = origin or (affected[0] if affected else label)
    recall = {}
    try:
        r = assistant.recall(recall_topic)
        recall = {"topic": recall_topic, "tried_before": r.tried_before,
                  "hits": r.total_hits, "headline": r.headline}
    except Exception:  # noqa: BLE001
        pass

    context = (f"[{etype}] {label} — origin={origin or '?'} · affected={affected[:5]} · "
               f"prior research {recall.get('hits', 0)}")
    return {"event_type": etype, "origin": origin, "affected_entities": affected,
            "impact_chain": chain, "historical_recall": recall, "research_context": context,
            "label": label, "requires_human_review": True, "is_advisory": True, "is_decision": False}


def stream(events, *, assistant=None) -> dict:
    """data events 배치 → 연구 이벤트 스트림 + 사람 검토 큐(결정적)."""
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    research_events = [classify_event(e, assistant=assistant) for e in (events or [])]
    by_type: dict = {}
    for re_ in research_events:
        by_type[re_["event_type"]] = by_type.get(re_["event_type"], 0) + 1
    return {"research_events": research_events, "count": len(research_events),
            "by_type": by_type,
            "human_review_queue": [{"label": e["label"], "event_type": e["event_type"],
                                    "affected": e["affected_entities"][:3],
                                    "prior_research": e["historical_recall"].get("hits", 0)}
                                   for e in research_events],
            "is_advisory": True, "is_decision": False,
            "note": "data event → 연구 컨텍스트(읽기전용) — 두 번째 이벤트 DB 없음, 신호 아님."}
