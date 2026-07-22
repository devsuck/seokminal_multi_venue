"""Execution Risk 검증 (P8.5) — 해시체인 무결성·결정적 재현·중복 탐지. 읽기전용.

verify_chain: 각 이벤트 previous_hash == 직전 report_hash. replay: 동일입력 재평가 동일.
**어떤 것도 변경/집행하지 않음.**
"""
from __future__ import annotations

from jarvis.execution_risk import ledger
from jarvis.execution_risk.models import GENESIS


def verify_chain() -> dict:
    evs = ledger.read_events()
    if not evs:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev = GENESIS
    seen = set()
    for i, e in enumerate(evs):
        if e.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not e.get("report_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_report_hash"}
        if e.get("event_id") in seen:
            return {"ok": False, "broken_at": i, "reason": "duplicate_event_id"}
        seen.add(e.get("event_id"))
        prev = e["report_hash"]
    return {"ok": True, "n": len(evs), "reason": "chain_intact"}


def replay(engine, request, context, policy=None, now: str = "") -> dict:
    """동일 입력 재평가 → 동일 report_hash(결정성 확인)."""
    r1 = engine.evaluate(request, context, policy, now)
    r2 = engine.evaluate(request, context, policy, now)
    return {"deterministic": r1.report_hash == r2.report_hash and r1.to_dict() == r2.to_dict(),
            "report_hash": r1.report_hash, "overall_status": r1.overall_status}
