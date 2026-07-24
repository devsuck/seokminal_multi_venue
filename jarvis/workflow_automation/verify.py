"""Workflow Automation 검증 (P44) — 체인·중복·워크플로/태스크 생애주기·의존성·검토·계보·재현. 읽기전용."""
from __future__ import annotations

from jarvis.workflow_automation import ledger
from jarvis.workflow_automation import models as M
from jarvis.workflow_automation.models import GENESIS, content_hash, detect_cycle_check


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


def _group(records, key) -> dict:
    out: dict = {}
    for r in records:
        out.setdefault(r.get(key), []).append(r)
    return out


def workflow_lifecycle_integrity() -> dict:
    issues: list = []
    for wid, evs in sorted(_group(ledger.read_workflow_events(), "workflow_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.W_CREATED:
                    issues.append(f"bad_initial:{wid}:{to}")
            elif not M.can_workflow_transition(prev, to):
                issues.append(f"invalid_transition:{wid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def task_lifecycle_integrity() -> dict:
    issues: list = []
    wf_ids = set(ledger.workflow_ids())
    for tid, evs in sorted(_group(ledger.read_task_events(), "task_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.T_PENDING:
                    issues.append(f"bad_initial_task:{tid}:{to}")
                if ev.get("workflow_id") not in wf_ids:
                    issues.append(f"orphan_task:{tid}")
            elif not M.can_task_transition(prev, to):
                issues.append(f"invalid_task_transition:{tid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    seen: set = set()
    for ev in ledger.read_workflow_events():
        if ev.get("from_state") == GENESIS:
            wid = ev.get("workflow_id")
            if wid in seen:
                issues.append(f"duplicate_workflow:{wid}")
            seen.add(wid)
    seen_t: set = set()
    for ev in ledger.read_task_events():
        if ev.get("from_state") == GENESIS:
            tid = ev.get("task_id")
            if tid in seen_t:
                issues.append(f"duplicate_task:{tid}")
            seen_t.add(tid)
    for records, idf, label in ((ledger.read_dependencies(), "dependency_id", "dependency"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def dependency_integrity() -> dict:
    issues: list = []
    all_tasks = {r.get("task_id") for r in ledger.read_task_events()}
    for wf in ledger.workflow_ids():
        deps = ledger.dependencies_for(wf)
        edges = []
        for d in deps:
            frm, to = d.get("from_task"), d.get("to_task")
            if frm not in all_tasks:
                issues.append(f"orphan_from:{d.get('dependency_id')}")
            if to not in all_tasks:
                issues.append(f"orphan_to:{d.get('dependency_id')}")
            if frm == to:
                issues.append(f"self_dependency:{d.get('dependency_id')}")
            edges.append((frm, to))
        if detect_cycle_check(edges):
            issues.append(f"cycle_dependency:{wf}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def approval_integrity() -> dict:
    """검토 요청은 절대 자동 승인되지 않는다 — is_granted 는 항상 False 이어야 한다."""
    issues: list = []
    wf_ids = set(ledger.workflow_ids())
    for a in ledger.read_approvals():
        if a.get("is_granted") is not False:
            issues.append(f"auto_granted:{a.get('approval_id')}")
        if a.get("status") != M.REVIEW_PENDING:
            issues.append(f"bad_review_status:{a.get('approval_id')}")
        if a.get("workflow_id") not in wf_ids:
            issues.append(f"orphan_approval:{a.get('approval_id')}")
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
    workflow = workflow_lifecycle_integrity()
    task = task_lifecycle_integrity()
    duplicate = duplicate_integrity()
    dependency = dependency_integrity()
    approval = approval_integrity()
    lineage = lineage_integrity()
    ok = (ok and workflow["ok"] and task["ok"] and duplicate["ok"] and dependency["ok"]
          and approval["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "workflow_lifecycle": workflow,
            "task_lifecycle": task, "duplicate": duplicate, "dependency": dependency,
            "approval": approval, "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_workflow_report("SYSTEM", now, commit=False)
    p2 = engine.generate_workflow_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "workflow_count": r1.workflow_count, "task_count": r1.task_count}
