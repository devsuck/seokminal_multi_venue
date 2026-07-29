"""Security Audit 검증 (P38) — 체인·중복·발견상태·계보·재현. 읽기전용."""
from __future__ import annotations

from jarvis.security_audit import ledger
from jarvis.security_audit import models as M
from jarvis.security_audit.models import GENESIS, content_hash


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


def finding_integrity() -> dict:
    issues: list = []
    for f in ledger.read_findings():
        if f.get("status") not in M.AUDIT_STATUSES:
            issues.append(f"invalid_status:{f.get('finding_id')}")
        if f.get("dimension") not in M.AUDIT_DIMENSIONS:
            issues.append(f"invalid_dimension:{f.get('finding_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    for records, idf, label in ((ledger.read_audits(), "audit_id", "audit"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    issues: list = []
    arts = ledger.read_artifacts()
    aids = {a.get("artifact_id") for a in arts}
    for a in arts:
        parent = a.get("parent_artifact")
        if parent and parent not in aids:
            issues.append(f"missing_parent:{a.get('artifact_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    finding = finding_integrity()
    duplicate = duplicate_integrity()
    lineage = lineage_integrity()
    ok = ok and finding["ok"] and duplicate["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "finding": finding, "duplicate": duplicate,
            "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    a1 = engine.run_full_audit("SYSTEM", now, commit=False)
    a2 = engine.run_full_audit("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict()
            and a1["findings"] == a2["findings"],
            "target_count": r1.target_count, "all_secure": a1["all_secure"]}
