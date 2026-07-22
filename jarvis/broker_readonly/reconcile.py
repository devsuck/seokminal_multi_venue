"""Reconciliation (P7.1) — PaperPosition vs BrokerPosition 대조. 결정적·읽기전용.

paper 심볼 = strategy_id(페이퍼 모델 규약). broker 심볼 = symbol.
"""
from __future__ import annotations

from jarvis.broker_readonly.models import ReconciliationReport

_EPS = 1e-9


def reconcile(paper_positions: list, broker_positions: list, now: str = "") -> ReconciliationReport:
    """paper(list[dict]) vs broker(list[BrokerPosition|dict]) → ReconciliationReport."""
    paper = {p["strategy_id"]: p for p in paper_positions}
    broker = {}
    for b in broker_positions:
        d = b.to_dict() if hasattr(b, "to_dict") else b
        broker[d["symbol"]] = d

    matched = sorted(set(paper) & set(broker))
    missing_in_broker = sorted(set(paper) - set(broker))
    missing_in_paper = sorted(set(broker) - set(paper))

    qty_diff: dict = {}
    val_diff: dict = {}
    for sym in matched:
        pq = float(paper[sym].get("quantity", 0.0))
        bq = float(broker[sym].get("quantity", 0.0))
        pv = float(paper[sym].get("market_value", 0.0))
        bv = float(broker[sym].get("market_value", 0.0))
        if abs(pq - bq) > _EPS:
            qty_diff[sym] = round(pq - bq, 8)
        if abs(pv - bv) > _EPS:
            val_diff[sym] = round(pv - bv, 4)

    return ReconciliationReport(
        timestamp=now, matched=matched, missing_in_broker=missing_in_broker,
        missing_in_paper=missing_in_paper, quantity_difference=qty_diff,
        value_difference=val_diff)
