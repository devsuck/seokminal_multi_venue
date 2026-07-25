"""Insider & Institutional Flow Intelligence (P98) — 내부자/기관 흐름을 **연구 트리거**로. **매수 신호 아님.**

Transaction → Event → Historical Context → Research Opportunity. 소스: DART·SEC Form 4·13F·기관 보유.
예: 하락 후 CEO 매수 + 섹터 저평가 + 과거 유사 = Insider Conviction Event. **재사용**: recall(과거),
event_intelligence, opportunity_discovery. **이것은 매수 신호가 아니라 연구 트리거일 뿐.**

원칙(문서 §Constitution, §P98): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class InsiderEvent:
    entity: str
    transaction_type: str      # BUY | SELL | CLUSTER_BUY | INSTITUTIONAL_ADD | ...
    size: float
    source: str                # DART | SEC_FORM4 | F13 | HOLDINGS
    historical_comparison: dict
    confidence: str
    related_research: str
    is_research_trigger: bool = True
    is_trade_signal: bool = False
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_transaction(txn: dict, *, assistant=None) -> InsiderEvent:
    """내부자/기관 거래 1건 → Insider Event(결정적). 연구 트리거일 뿐, 신호 아님."""
    t = txn or {}
    entity = str(t.get("entity") or t.get("company") or t.get("symbol") or "").strip()
    ttype = str(t.get("type") or t.get("transaction_type") or "BUY").upper()
    size = _num(t.get("size") or t.get("shares") or t.get("value")) or 0.0
    prior_return = _num(t.get("prior_return"))       # 사전 주가 흐름
    role = str(t.get("role", "")).lower()
    clustered = bool(t.get("cluster") or (t.get("n_insiders") and _num(t.get("n_insiders")) and _num(t["n_insiders"]) >= 3))

    # 확신 이벤트 판정: 하락 후 매수 + (경영진/클러스터)
    conviction = (ttype.startswith("BUY") and prior_return is not None and prior_return < 0
                  and (role in ("ceo", "cfo", "chairman") or clustered))
    if conviction:
        ttype = "CONVICTION_BUY"
    elif clustered and ttype.startswith("BUY"):
        ttype = "CLUSTER_BUY"

    # 과거 비교 — recall 재사용
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    hist = {}
    try:
        r = assistant.recall(entity)
        hist = {"prior_records": r.total_hits, "tried_before": r.tried_before}
    except Exception:  # noqa: BLE001
        pass

    confidence = "HIGH" if conviction else "MEDIUM" if (clustered or size >= 1e6) else "LOW"
    return InsiderEvent(entity=entity or "unknown", transaction_type=ttype, size=size,
                        source=str(t.get("source", "insider")),
                        historical_comparison={"prior_return": prior_return, **hist},
                        confidence=confidence,
                        related_research=f"recall({entity}) prior={hist.get('prior_records', 0)}")


def stream(txns, *, assistant=None) -> dict:
    """내부자/기관 거래 배치 → Insider Event 스트림 + 연구 트리거 큐(읽기전용)."""
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine()
    events = [analyze_transaction(t, assistant=assistant) for t in (txns or [])]
    triggers = [e for e in events if e.confidence in ("HIGH", "MEDIUM")]
    by_type: dict = {}
    for e in events:
        by_type[e.transaction_type] = by_type.get(e.transaction_type, 0) + 1
    return {"events": [e.to_dict() for e in events], "count": len(events), "by_type": by_type,
            "research_triggers": [{"entity": e.entity, "type": e.transaction_type,
                                   "confidence": e.confidence} for e in triggers],
            "is_advisory": True, "is_decision": False,
            "note": "내부자/기관 흐름 → 연구 트리거(읽기전용). 매수 신호가 아니다 — 사람 검토."}
