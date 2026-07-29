"""Event Driven Research Trigger (P101) — 시장 지능 이벤트를 **연구 태스크**로 연결한다. **거래 신호 아님.**

Market Intelligence event(P86·P96-100) → Opportunity Candidate → Hypothesis. 이 모듈은 오직 **연구 태스크**를
만든다 — 트레이드 신호가 아니다. **재사용**: event_stream.classify_event, opportunity_discovery.discover,
hypothesis_generator.generate. 새 원장/엔진/DB 없음. 결정적·읽기전용·사람 결정.

원칙(문서 §Constitution, §P101): 통합·조율만. 결정적. 거래·집행·자본배분 없음.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from jarvis.research_workflow import models as M

# 이벤트 유형(문자열) → (트리거 유형, opportunity 신호 유형, 연구 영역). 결정적 매핑.
_TRIGGER_MAP = (
    ("EARNINGS", "earnings_reaction_study", "price_fundamental_divergence",
     "post-earnings drift / surprise reaction"),
    ("SUPPLY", "supply_lead_lag_study", "supply_disruption",
     "supply-chain lead-lag propagation"),
    ("INSIDER", "insider_conviction_study", "insider_anomaly",
     "insider conviction follow-through"),
    ("REGULAT", "regulatory_event_study", "macro_shock", "regulatory/event impact"),
    ("MA_", "ma_arbitrage_study", "price_fundamental_divergence", "M&A re-rating"),
    ("MACRO", "macro_regime_study", "macro_shock", "macro regime factor re-evaluation"),
    ("VOLATIL", "volatility_regime_study", "sentiment_extreme", "volatility regime shift"),
    ("PRICE", "price_dislocation_study", "price_fundamental_divergence",
     "price dislocation / mean reversion"),
    ("VOLUME", "liquidity_study", "liquidity_imbalance", "liquidity/flow imbalance"),
    ("SENTIMENT", "sentiment_extreme_study", "sentiment_extreme", "sentiment extreme contrarian"),
    ("SECTOR", "sector_rotation_study", "sector_rotation", "sector rotation relative strength"),
)
_DEFAULT_TRIGGER = ("general_research_study", "macro_shock", "general market observation")


@dataclass(frozen=True)
class ResearchTrigger:
    event_id: str
    trigger_type: str
    related_assets: list
    affected_sector: str
    historical_context: dict
    suggested_research_area: str
    confidence: str                 # LOW | MEDIUM | HIGH
    is_research_task: bool = True    # 연구 태스크만 — 신호 아님
    is_trade_signal: bool = False
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _map(event_type: str) -> tuple:
    et = (event_type or "").upper()
    for key, trig, opp, area in _TRIGGER_MAP:
        if key in et:
            return trig, opp, area
    return _DEFAULT_TRIGGER


def from_event(event: dict, *, assistant=None) -> ResearchTrigger:
    """시장 지능 이벤트 → ResearchTrigger(결정적). 연구 태스크 생성 — 절대 트레이드 신호 아님."""
    from jarvis.research_workflow.event_stream import classify_event
    ev = classify_event(event or {}, assistant=assistant)
    trig, _opp, area = _map(ev["event_type"])
    affected = ev.get("affected_entities", []) or []
    # 섹터 = 대문자 짧은 심볼(ETF/섹터 노드)
    sectors = [e for e in affected if e.isupper() and len(e) <= 4]
    recall = ev.get("historical_recall", {}) or {}
    hits = int(recall.get("hits", 0) or 0)
    confidence = "HIGH" if (hits and len(affected) >= 2) else "MEDIUM" if (hits or affected) else "LOW"
    event_id = M.input_digest("trigger", ev.get("event_type"), ev.get("origin"), ev.get("label"))
    return ResearchTrigger(
        event_id=event_id, trigger_type=trig,
        related_assets=[a for a in affected if a not in sectors] or ([ev["origin"]] if ev.get("origin") else []),
        affected_sector=sectors[0] if sectors else "",
        historical_context={"topic": recall.get("topic", ev.get("origin", "")),
                            "prior_research": hits, "tried_before": recall.get("tried_before", False)},
        suggested_research_area=area, confidence=confidence)


def dispatch(event: dict, *, assistant=None, limit: int = 3) -> dict:
    """이벤트 → 트리거 → Opportunity Candidate → 가설 후보(연구 태스크 체인). 읽기전용·결정적.

    Event → Opportunity → Hypothesis 를 기존 엔진으로 조율한다. 자동 실행/거래 없음 — 사람 검토 큐.
    """
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    trigger = from_event(event, assistant=assistant)
    _trig, opp_type, _area = _map(_classify_type(event, assistant))

    # Opportunity Candidate — opportunity_discovery 재사용
    entity = (trigger.related_assets[0] if trigger.related_assets else "")
    opportunities = []
    try:
        from jarvis.research_workflow.opportunity_discovery import discover
        od = discover({opp_type: {"entity": entity, "evidence": trigger.related_assets}},
                      assistant=assistant)
        opportunities = od.get("opportunities", [])
    except Exception:  # noqa: BLE001
        pass

    # Hypothesis 후보 — hypothesis_generator 재사용(연구 태스크만)
    hypotheses = []
    try:
        from jarvis.research_workflow.hypothesis_generator import HypothesisGenerator
        topic = entity or trigger.suggested_research_area
        hyps = HypothesisGenerator(assistant=assistant).generate(topic, limit=limit)
        hypotheses = [h.to_dict() for h in hyps][:limit]
    except Exception:  # noqa: BLE001
        pass

    return {"trigger": trigger.to_dict(), "opportunity_candidates": opportunities,
            "suggested_hypotheses": hypotheses,
            "research_tasks": [{"area": trigger.suggested_research_area,
                               "assets": trigger.related_assets, "confidence": trigger.confidence}],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "is_trade_signal": False,
            "note": "이벤트 → 연구 태스크(읽기전용) — Opportunity→Hypothesis 조율. 트레이드 신호 아님."}


def _classify_type(event, assistant) -> str:
    from jarvis.research_workflow.event_stream import classify_event
    return classify_event(event or {}, assistant=assistant)["event_type"]
