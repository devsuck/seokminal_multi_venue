"""Fill Reconciliation 검증 (P8.3) — 해시체인 무결성·결정적 재현. 읽기전용.

verify_chain: 각 이벤트 report_hash 존재 + previous_hash 연결 확인.
**어떤 것도 변경/집행하지 않음.**
"""
from __future__ import annotations

from jarvis.fill_reconciliation import ledger
from jarvis.fill_reconciliation.models import GENESIS


def verify_chain() -> dict:
    """previous_hash 연결 무결성. 각 이벤트의 previous_hash == 직전 이벤트 report_hash."""
    evs = ledger.read_events()
    if not evs:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev = GENESIS
    for i, e in enumerate(evs):
        if e.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not e.get("report_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_report_hash"}
        prev = e["report_hash"]
    return {"ok": True, "n": len(evs), "reason": "chain_intact"}


def replay(engine, record, fills, now: str = "", **kw) -> dict:
    """동일 입력 재대조 → 동일 report_hash(결정성 확인)."""
    r1 = engine.reconcile(record, fills, now, **kw)
    r2 = engine.reconcile(record, fills, now, **kw)
    return {"deterministic": r1.report_hash == r2.report_hash and r1.to_dict() == r2.to_dict(),
            "report_hash": r1.report_hash, "status": r1.status}
