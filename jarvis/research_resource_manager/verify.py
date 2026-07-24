"""Research Resource Manager 검증 (P32) — 체인·중복·배분(자동/프로비저닝 금지)·사용·예산·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 배분 무결성(is_provisioned=False·is_auto=False).
사용/예산 무결성(알려진 자원 참조·유형 유효). 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_resource_manager import ledger
from jarvis.research_resource_manager import models as M
from jarvis.research_resource_manager.models import GENESIS, content_hash, detect_cycle_check


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


def allocation_integrity() -> dict:
    """배분 무결성: 모든 배분 is_provisioned=False·is_auto=False(기록만·자동 배분/프로비저닝 금지)."""
    issues: list = []
    for a in ledger.read_allocations():
        if a.get("is_provisioned") is not False:
            issues.append(f"provisioned_allocation:{a.get('allocation_id')}")
        if a.get("is_auto") is not False:
            issues.append(f"auto_allocation:{a.get('allocation_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """사용/배분 무결성: 알려진 자원 참조 + 자원/사용/예산 유형 유효."""
    issues: list = []
    res_ids = set(ledger.resource_ids())
    for r in ledger.read_resources():
        if r.get("resource_type") not in M.RESOURCE_TYPES:
            issues.append(f"invalid_resource_type:{r.get('resource_id')}")
    for u in ledger.read_usage():
        if u.get("resource_id") not in res_ids:
            issues.append(f"orphan_usage:{u.get('usage_id')}")
        if u.get("purpose") not in M.USAGE_PURPOSES:
            issues.append(f"invalid_purpose:{u.get('usage_id')}")
    for a in ledger.read_allocations():
        if a.get("resource_id") not in res_ids:
            issues.append(f"orphan_allocation:{a.get('allocation_id')}")
    for b in ledger.read_budgets():
        if b.get("category") not in M.BUDGET_CATEGORIES:
            issues.append(f"invalid_budget_category:{b.get('budget_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    for records, idf, label in ((ledger.read_resources(), "resource_id", "resource"),
                                (ledger.read_budgets(), "budget_id", "budget"),
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
    allocation = allocation_integrity()
    reference = reference_integrity()
    duplicate = duplicate_integrity()
    lineage = lineage_integrity()
    ok = ok and allocation["ok"] and reference["ok"] and duplicate["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "allocation": allocation,
            "reference": reference, "duplicate": duplicate, "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    u1 = engine.all_utilizations()
    u2 = engine.all_utilizations()
    return {"deterministic": r1.to_dict() == r2.to_dict() and u1 == u2,
            "resource_count": r1.resource_count, "allocation_count": r1.allocation_count}
