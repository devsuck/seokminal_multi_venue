"""News Intelligence Layer (P97) — 뉴스를 **구조화된 연구 이벤트**로 변환한다. **읽기 전용, 별도 DB 없음.**

Headline/article → Research Event(type·affected companies·sectors·relevance·historical similarity·
related research). **재사용**: knowledge graph·supply chain graph(event_intelligence)·memory recall.
별도 뉴스 인텔리전스 데이터베이스를 만들지 않는다.

원칙(문서 §Constitution, §P97): 통합·조율만. 결정적. 거래·집행·신호 없음.
"""
from __future__ import annotations

# 헤드라인 키워드 → 뉴스 이벤트 유형(결정적)
_NEWS_TYPES = (
    (("supplier", "supply", "production", "capacity", "factory", "fab", "shortage"), "SUPPLY_CHAIN_CHANGE"),
    (("earnings", "revenue", "profit", "guidance", "beat", "miss", "eps"), "EARNINGS_NEWS"),
    (("acquire", "merger", "acquisition", "buyout", "deal"), "MA_NEWS"),
    (("lawsuit", "regulator", "antitrust", "ban", "sanction", "probe"), "REGULATORY"),
    (("launch", "product", "unveil", "release", "chip", "model"), "PRODUCT_NEWS"),
    (("insider", "ceo buys", "stake"), "INSIDER_NEWS"),
)


def _classify(text: str) -> str:
    low = (text or "").lower()
    for kws, typ in _NEWS_TYPES:
        if any(k in low for k in kws):
            return typ
    return "GENERAL_NEWS"


def _relevance(affected, recall_hits) -> str:
    score = len(affected) + (1 if recall_hits else 0)
    return "HIGH" if score >= 3 else "MEDIUM" if score >= 1 else "LOW"


def analyze_headline(text: str, *, entity: str = "", assistant=None) -> dict:
    """헤드라인 → 연구 이벤트(유형·영향기업·섹터·관련성·과거유사·관련연구). 결정적·읽기전용."""
    etype = _classify(text)
    # 영향 기업/섹터 — event_intelligence(공급망/관계 그래프) 재사용
    affected, sectors, path = [], [], {"nodes": [], "edges": []}
    origin = entity
    try:
        from jarvis.research_assistant.event_intelligence import MarketEventIntelligence
        mei = MarketEventIntelligence()
        imp = mei.analyze_event({"text": text, "entity": entity} if entity else {"text": text})
        origin = origin or imp.origin
        affected = imp.affected_entities
        path = imp.impact_chain
        # 섹터 = 그래프에서 ETF/섹터 노드(대문자 짧은 심볼)
        sectors = [e for e in affected if e.isupper() and len(e) <= 4]
    except Exception:  # noqa: BLE001
        pass

    # 과거 유사·관련 연구 — recall 재사용
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    recall_topic = origin or (affected[0] if affected else text)
    recall = {}
    try:
        r = assistant.recall(recall_topic)
        recall = {"topic": recall_topic, "tried_before": r.tried_before, "hits": r.total_hits}
    except Exception:  # noqa: BLE001
        pass

    return {"headline": text, "event_type": etype, "origin": origin,
            "affected_companies": [e for e in affected if e not in sectors],
            "affected_sectors": sectors, "relevance_score": _relevance(affected, recall.get("hits", 0)),
            "historical_similarity": recall, "related_research": f"recall({recall_topic}) hits={recall.get('hits', 0)}",
            "impact_path": path, "requires_human_review": True,
            "is_advisory": True, "is_decision": False, "is_trade_signal": False}


def stream(headlines, *, assistant=None) -> dict:
    """헤드라인 배치 → 연구 이벤트 스트림 + 검토 큐(읽기전용)."""
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    items = []
    for h in (headlines or []):
        text = h.get("text") if isinstance(h, dict) else str(h)
        entity = h.get("entity", "") if isinstance(h, dict) else ""
        items.append(analyze_headline(text, entity=entity, assistant=assistant))
    by_type: dict = {}
    for it in items:
        by_type[it["event_type"]] = by_type.get(it["event_type"], 0) + 1
    return {"events": items, "count": len(items), "by_type": by_type,
            "review_queue": [{"headline": i["headline"], "event_type": i["event_type"],
                              "relevance": i["relevance_score"], "affected": i["affected_companies"][:3]}
                             for i in items],
            "is_advisory": True, "is_decision": False,
            "note": "뉴스 → 연구 컨텍스트(읽기전용) — 별도 뉴스 DB 없음, 신호 아님."}
