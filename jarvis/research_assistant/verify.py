"""Research Assistant 검증 (P44) — 체인·자문 비구속·결정 없음·재현. 읽기전용."""
from __future__ import annotations

from jarvis.research_assistant import ledger
from jarvis.research_assistant.models import GENESIS, content_hash


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


def advisory_integrity() -> dict:
    """모든 리포트는 is_decision=False·is_advisory=True, 모든 노트는 is_binding=False 이어야 한다."""
    issues = []
    for r in ledger.read_reports():
        if r.get("is_decision") is not False:
            issues.append(f"decision_report:{r.get('report_id')}")
        if r.get("is_advisory") is not True:
            issues.append(f"non_advisory_report:{r.get('report_id')}")
    for n in ledger.read_notes():
        if n.get("is_binding") is not False:
            issues.append(f"binding_note:{n.get('note_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    advisory = advisory_integrity()
    ok = ok and advisory["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "advisory": advisory}


def replay(engine, now="") -> dict:
    b1 = engine.build_bundle()
    b2 = engine.build_bundle()
    r1 = engine.generate_report("DAILY", now, commit=False)
    r2 = engine.generate_report("DAILY", now, commit=False)
    return {"deterministic": b1 == b2 and r1.to_dict() == r2.to_dict(),
            "bundle_digest": r1.bundle_digest}
