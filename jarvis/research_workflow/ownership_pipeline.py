"""Insider & Ownership Intelligence (P116) — 내부자/기관 소유 변화를 연결한다. **연구 트리거일 뿐.**

연결: Insider transactions·Institutional ownership·Fund flows. Ownership Event 생성
{company·actor·transaction·size·date·historical_context}. **재사용**: providers.InsiderProvider +
insider_flow.analyze_transaction(P98). **매수 신호 아님 — 연구 트리거.** 새 저장소 없음.

원칙(문서 §Constitution, §P116): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def _ownership_event(txn: dict, ev) -> dict:
    """InsiderEvent + raw → Ownership Event(스펙 필드: company·actor·transaction·size·date·historical)."""
    t = txn or {}
    return {"company": ev.entity, "actor": str(t.get("actor") or t.get("role") or t.get("insider") or ""),
            "transaction": ev.transaction_type, "size": ev.size,
            "date": str(t.get("date") or t.get("timestamp") or ""),
            "source": ev.source, "confidence": ev.confidence,
            "historical_context": ev.historical_comparison,
            "is_research_trigger": True, "is_trade_signal": False, "requires_human_review": True}


def run(transactions, *, source: str = "ownership", assistant=None) -> dict:
    """내부자/기관 소유 변화 배치 → Ownership Event + 연구 트리거 큐. analyze_transaction 재사용."""
    from jarvis.research_workflow.insider_flow import analyze_transaction
    events = []
    by_type: dict = {}
    for t in (transactions or []):
        ev = analyze_transaction(t, assistant=assistant)
        by_type[ev.transaction_type] = by_type.get(ev.transaction_type, 0) + 1
        events.append(_ownership_event(t, ev))
    triggers = [e for e in events if e["confidence"] in ("HIGH", "MEDIUM")]
    return {"ownership_events": events, "count": len(events), "by_type": by_type,
            "source": source, "pipeline": "ownership",
            "research_triggers": [{"company": e["company"], "transaction": e["transaction"],
                                   "confidence": e["confidence"]} for e in triggers],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("소유/내부자 파이프라인(읽기전용) — Ownership Event 생성. 매수 신호가 아니라 연구 트리거. "
                     "새 저장소 없음, 거래·집행 없음.")}
