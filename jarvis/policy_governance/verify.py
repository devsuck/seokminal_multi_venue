"""Policy Governance 검증 (P9.7) — 해시체인 무결성·변조 탐지·중복 탐지·리플레이. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. replay: 동일 정책 재등록/
스냅샷/drift 재현 → 동일 해시(결정성). **변경/집행/설정변경 없음.**
"""
from __future__ import annotations

from jarvis.policy_governance import ledger
from jarvis.policy_governance.models import GENESIS, content_hash


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


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results}


def replay(engine, now: str = "") -> dict:
    """동일 상태에서 스냅샷·거버넌스 리포트 재계산 → 동일 해시(결정성). commit 없음."""
    s1 = engine.snapshot(now, commit=False)
    s2 = engine.snapshot(now, commit=False)
    r1 = engine.governance_report(now)
    r2 = engine.governance_report(now)
    return {"deterministic": (s1.to_dict() == s2.to_dict() and r1.to_dict() == r2.to_dict()),
            "snapshot_id": s1.snapshot_id,
            "configuration_hash": s1.configuration_hash,
            "compliance_score": r1.compliance_score}
