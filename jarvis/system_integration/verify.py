"""System Integration 검증 (P35) — 체인·중복·발견상태·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 발견 무결성(상태·검증 유형 유효). 아티팩트 계보.
**변경 없음.**
"""
from __future__ import annotations

from jarvis.system_integration import ledger
from jarvis.system_integration import models as M
from jarvis.system_integration.models import GENESIS, content_hash, detect_cycle_check


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
    """발견 무결성: 상태·검증 유형 유효."""
    issues: list = []
    for f in ledger.read_findings():
        if f.get("status") not in M.CHECK_STATUSES:
            issues.append(f"invalid_status:{f.get('finding_id')}")
        if f.get("check_type") not in M.CHECK_TYPES:
            issues.append(f"invalid_check_type:{f.get('finding_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    for records, idf, label in ((ledger.read_validations(), "validation_id", "validation"),
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
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in aids:
                issues.append(f"missing_parent:{a.get('artifact_id')}")
            edges.append((a.get("artifact_id"), parent))
    if detect_cycle_check(edges):
        issues.append("cycle_artifact")
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
    a1 = engine.architecture_summary()
    a2 = engine.architecture_summary()
    d1 = engine.dependency_graph()
    d2 = engine.dependency_graph()
    return {"deterministic": r1.to_dict() == r2.to_dict() and a1 == a2 and d1 == d2,
            "layer_count": r1.layer_count, "validation_count": r1.validation_count}
