"""Post-Trade Analytics 검증 (P8.7) — 해시체인 무결성·결정적 재현·중복 탐지. 읽기전용.

verify_chain: 각 리포트 previous_hash == 직전 report_hash. replay: 동일입력 재분석 동일.
**어떤 것도 변경/집행하지 않음.**
"""
from __future__ import annotations

from jarvis.post_trade_analytics import ledger
from jarvis.post_trade_analytics.models import GENESIS


def verify_chain() -> dict:
    reps = ledger.read_reports()
    if not reps:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev = GENESIS
    seen = set()
    for i, r in enumerate(reps):
        if r.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not r.get("report_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_report_hash"}
        if r.get("report_id") in seen:
            return {"ok": False, "broken_at": i, "reason": "duplicate_report_id"}
        seen.add(r.get("report_id"))
        prev = r["report_hash"]
    return {"ok": True, "n": len(reps), "reason": "chain_intact"}


def replay(engine, request_id: str, execution, now: str = "", **kw) -> dict:
    """동일 입력 재분석 → 동일 report_hash(결정성 확인)."""
    r1 = engine.analyze(request_id, execution, now, **kw)
    r2 = engine.analyze(request_id, execution, now, **kw)
    return {"deterministic": r1.report_hash == r2.report_hash and r1.to_dict() == r2.to_dict(),
            "report_hash": r1.report_hash, "overall_status": r1.overall_status}
