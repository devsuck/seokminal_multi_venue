"""Local Runtime 검증 (P42) — 체인·이벤트 정합·재현. 읽기전용."""
from __future__ import annotations

from jarvis.local_runtime import ledger
from jarvis.local_runtime import models as M
from jarvis.local_runtime.models import GENESIS, content_hash


def _verify_records(records, id_field) -> dict:
    if not records:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev = GENESIS
    seen = set()
    for i, r in enumerate(records):
        if r.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_record_hash"}
        rid = r.get(id_field)
        if rid in seen:
            return {"ok": False, "broken_at": i, "reason": "duplicate_id"}
        if content_hash(r) != r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "record_hash_mismatch"}
        seen.add(rid)
        prev = r["record_hash"]
    return {"ok": True, "n": len(records), "reason": "chain_intact"}


def verify_ledger(which) -> dict:
    filename, id_field = which
    return _verify_records(ledger.read_jsonl(filename), id_field)


def event_integrity() -> dict:
    """모든 런타임 이벤트 kind 는 알려진 집합이어야 한다."""
    issues = []
    for e in ledger.read_events():
        if e.get("kind") not in M.EVENT_KINDS:
            issues.append(f"bad_kind:{e.get('event_id')}")
        if e.get("status") not in M.CHECK_STATES:
            issues.append(f"bad_status:{e.get('event_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    events = event_integrity()
    ok = ok and events["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "event_integrity": events}


def replay(engine, now="") -> dict:
    s1 = engine.summary(now)
    s2 = engine.summary(now)
    d1 = engine.discover_modules()
    d2 = engine.discover_modules()
    return {"deterministic": s1.to_dict() == s2.to_dict() and d1.to_dict() == d2.to_dict(),
            "event_count": s1.event_count, "module_count": d1.module_count}
