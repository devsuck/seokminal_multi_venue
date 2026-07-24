"""Experiment Tracking 검증 (P42) — 체인·중복·run/파라미터/결과 참조·비교·계보·재현. 읽기전용."""
from __future__ import annotations

from jarvis.experiment_tracking import ledger
from jarvis.experiment_tracking import models as M
from jarvis.experiment_tracking.models import GENESIS, content_hash, detect_cycle_check


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


def reference_integrity() -> dict:
    """참조 무결성: run→실험, 파라미터/결과→run, 비교→run 참조 유효 + run 상태 유효."""
    issues: list = []
    exp_ids = {e.get("experiment_id") for e in ledger.read_experiments()}
    run_ids = {r.get("run_id") for r in ledger.read_runs()}
    for r in ledger.read_runs():
        if r.get("experiment_id") not in exp_ids:
            issues.append(f"orphan_run:{r.get('run_id')}")
        if r.get("status") not in M.RUN_STATUSES:
            issues.append(f"invalid_status:{r.get('run_id')}")
    for p in ledger.read_parameters():
        if p.get("run_id") not in run_ids:
            issues.append(f"orphan_parameter:{p.get('parameter_id')}")
    for r in ledger.read_results():
        if r.get("run_id") not in run_ids:
            issues.append(f"orphan_result:{r.get('result_id')}")
    for c in ledger.read_comparisons():
        if c.get("run_a") not in run_ids or c.get("run_b") not in run_ids:
            issues.append(f"orphan_comparison:{c.get('comparison_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    for records, idf, label in ((ledger.read_experiments(), "experiment_id", "experiment"),
                                (ledger.read_runs(), "run_id", "run"),
                                (ledger.read_comparisons(), "comparison_id", "comparison"),
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
    reference = reference_integrity()
    duplicate = duplicate_integrity()
    lineage = lineage_integrity()
    ok = ok and reference["ok"] and duplicate["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "reference": reference,
            "duplicate": duplicate, "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "experiment_count": r1.experiment_count, "run_count": r1.run_count}
