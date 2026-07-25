"""Live Market Data Connection (P96) — 시장 데이터를 Research OS 이벤트 계층에 연결하는 **어댑터**. **거래 없음.**

Market Data → Normalizer → MarketEvent → Event Intelligence → Research Context → Opportunity/Review.
**정규화(normalizer)와 분석(event_intelligence)을 분리**한다. 원본 timestamp·source 보존. 새 DB 없음 —
정규화된 MarketEvent 는 기존 event_stream(P86)으로 흘러가 사람 검토 큐가 된다.

원칙(문서 §Constitution, §P96): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# 지표 → MarketEvent 유형(결정적 임계). 분석이 아니라 정규화만.
_MOVE_THRESHOLD = 0.05        # ±5% 가격 변동
_VOL_SPIKE = 0.4             # 연율 변동성
_VOLUME_SPIKE = 2.0         # 평균 대비 배수


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MarketEvent:
    source: str
    asset: str
    timestamp: str
    event_type: str
    metrics: dict
    confidence: str            # LOW | MEDIUM | HIGH
    related_entities: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _classify_metrics(m: dict) -> tuple:
    """지표 → (event_type, confidence). 정규화 규칙(결정적)."""
    ret = _num(m.get("return") or m.get("change_pct"))
    vol = _num(m.get("volatility"))
    volu = _num(m.get("volume_ratio"))
    if vol is not None and vol >= _VOL_SPIKE:
        return "VOLATILITY_SPIKE", "HIGH" if vol >= 0.6 else "MEDIUM"
    if ret is not None and abs(ret) >= _MOVE_THRESHOLD:
        return ("PRICE_SURGE" if ret > 0 else "PRICE_DROP"), "HIGH" if abs(ret) >= 0.1 else "MEDIUM"
    if volu is not None and volu >= _VOLUME_SPIKE:
        return "VOLUME_SPIKE", "MEDIUM"
    return "MARKET_UPDATE", "LOW"


def normalize(raw: dict, *, source: str = "") -> MarketEvent:
    """원시 시장 데이터 1건 → MarketEvent(정규화만, 분석 없음). 원본 timestamp·source 보존."""
    r = raw or {}
    asset = str(r.get("asset") or r.get("symbol") or r.get("instrument_id") or "").strip()
    metrics = r.get("metrics") if isinstance(r.get("metrics"), dict) else {
        k: r[k] for k in ("return", "change_pct", "volatility", "volume_ratio", "price", "close")
        if k in r}
    etype, conf = _classify_metrics(metrics)
    return MarketEvent(source=str(source or r.get("source", "market_data")), asset=asset,
                       timestamp=str(r.get("timestamp") or r.get("ts") or ""),
                       event_type=etype, metrics=metrics, confidence=conf, related_entities=[])


def to_research_event(mev: MarketEvent, *, assistant=None) -> dict:
    """MarketEvent → 연구 이벤트(event_stream 재사용: 영향개체·회상·연구컨텍스트)."""
    from jarvis.research_workflow.event_stream import classify_event
    ev = classify_event({"kind": "market", "entity": mev.asset,
                         "text": f"{mev.event_type} {mev.asset}", "source": mev.source},
                        assistant=assistant)
    ev["market_event"] = mev.to_dict()
    ev["source_event_type"] = mev.event_type
    ev["timestamp"] = mev.timestamp
    return ev


def ingest(raw_list, *, source: str = "", assistant=None) -> dict:
    """원시 시장 데이터 배치 → MarketEvent 정규화 → 연구 이벤트 스트림 + 검토 큐(읽기전용)."""
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    events = [normalize(r, source=source) for r in (raw_list or [])]
    research = [to_research_event(e, assistant=assistant) for e in events]
    by_type: dict = {}
    for e in events:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
    return {"source": source, "market_events": [e.to_dict() for e in events],
            "research_events": research, "count": len(events), "by_type": by_type,
            "review_queue": [{"asset": e.asset, "event_type": e.event_type,
                              "confidence": e.confidence, "timestamp": e.timestamp}
                             for e in events],
            "is_advisory": True, "is_decision": False,
            "note": "시장데이터 어댑터 — 정규화/연구컨텍스트만(읽기전용). 새 DB 없음, 거래·신호 없음."}
