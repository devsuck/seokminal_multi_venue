"""System Health 검증 (P9.1) — 해시체인 무결성·결정적 재현·중복 탐지·변조 탐지. 읽기전용.

verify_chain: 각 리포트 previous_hash == 직전 report_hash, report_hash 재계산 일치.
replay: 동일 probes 재관측 → 동일 report_hash(결정성). **어떤 것도 변경/집행하지 않음.**
"""
from __future__ import annotations

from jarvis.system_health import ledger
from jarvis.system_health.models import (
    GENESIS,
    health_score,
    input_hash,
    overall_status,
    report_hash,
    report_id,
)


def _recompute(r: dict) -> dict:
    """저장된 리포트로부터 해시를 재계산(변조 탐지)."""
    probes = r.get("subsystems", [])
    ih = input_hash(probes)
    rid = report_id(ih)
    statuses = [p.get("status") for p in probes]
    rh = report_hash(rid, overall_status(statuses), health_score(statuses),
                     probes, r.get("warnings", []), r.get("errors", []), ih)
    return {"input_hash": ih, "report_id": rid, "report_hash": rh}


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
        rc = _recompute(r)
        if rc["report_hash"] != r.get("report_hash"):
            return {"ok": False, "broken_at": i, "reason": "report_hash_mismatch"}
        if rc["input_hash"] != r.get("input_hash"):
            return {"ok": False, "broken_at": i, "reason": "input_hash_mismatch"}
        seen.add(r.get("report_id"))
        prev = r["report_hash"]
    return {"ok": True, "n": len(reps), "reason": "chain_intact"}


def replay(engine, now: str = "", *, probes=None) -> dict:
    """동일 probes 재관측 → 동일 report_hash(결정성 확인). 관측만."""
    r1 = engine.check(now, probes=probes)
    r2 = engine.check(now, probes=probes)
    return {"deterministic": r1.report_hash == r2.report_hash and r1.to_dict() == r2.to_dict(),
            "report_hash": r1.report_hash, "overall_status": r1.overall_status}
