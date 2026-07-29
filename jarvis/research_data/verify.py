"""Research Data 검증 (P10.1) — 체인 무결성·변조·중복·리플레이·lineage 무결성. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. lineage: 사이클 없음.
replay: 동일 상태 스냅샷 재현 → 동일 해시. **변경/집행 없음.**
"""
from __future__ import annotations

from jarvis.research_data import ledger
from jarvis.research_data.models import GENESIS, content_hash, detect_lineage_cycle


def _verify_records(records: list, id_field: str) -> dict:
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


def lineage_integrity() -> dict:
    """전체 lineage 그래프 사이클 검사."""
    edges = [(r.get("dataset_id"), r.get("parent_dataset"))
             for r in ledger.read_lineage() if r.get("parent_dataset")]
    cycle = detect_lineage_cycle(edges)
    return {"ok": not cycle, "cycle": cycle, "n_edges": len(edges)}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lin = lineage_integrity()
    ok = ok and lin["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lineage_integrity": lin}


def replay(engine, now: str = "") -> dict:
    """동일 상태 스냅샷 두 번 → 동일 해시(재현성). commit 없음."""
    s1 = engine.snapshot(now, commit=False)
    s2 = engine.snapshot(now, commit=False)
    return {"deterministic": s1.to_dict() == s2.to_dict(),
            "snapshot_id": s1.snapshot_id, "snapshot_hash": s1.snapshot_hash}
