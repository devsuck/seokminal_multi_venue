"""Execution Cost 검증 (P8.4) — 해시체인 무결성·결정적 재현. 읽기전용.

verify_chain: 각 이벤트 previous_hash == 직전 cost_hash. replay: 동일입력 재계산 동일.
**어떤 것도 변경/집행하지 않음.**
"""
from __future__ import annotations

from jarvis.execution_cost import ledger
from jarvis.execution_cost.models import GENESIS


def verify_chain() -> dict:
    evs = ledger.read_events()
    if not evs:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev = GENESIS
    for i, e in enumerate(evs):
        if e.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not e.get("cost_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_cost_hash"}
        prev = e["cost_hash"]
    return {"ok": True, "n": len(evs), "reason": "chain_intact"}


def replay(engine, inp, now: str = "", **kw) -> dict:
    """동일 입력 재계산 → 동일 report_hash(결정성 확인)."""
    r1 = engine.calculate(inp, now, **kw)
    r2 = engine.calculate(inp, now, **kw)
    return {"deterministic": r1.report_hash == r2.report_hash and r1.to_dict() == r2.to_dict(),
            "report_hash": r1.report_hash, "status": r1.status, "cost_bps": r1.cost_bps}
