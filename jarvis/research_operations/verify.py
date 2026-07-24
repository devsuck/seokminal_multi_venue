"""Research Operations 검증 (P18) — 체인·변조·중복·생애주기·의존(DAG)·참조·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 워크플로/작업 생애주기 전이 합법성(genesis 시작).
중복 워크플로/작업(genesis 유일). 의존 그래프(dangling·순환). 참조 무결성(작업/의존/런→워크플로). 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_operations import ledger
from jarvis.research_operations.models import (
    T_CREATED,
    W_DRAFT,
    GENESIS,
    can_task_transition,
    can_workflow_transition,
    content_hash,
    detect_cycle,
)


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


def _group(records: list, key: str) -> dict:
    out: dict = {}
    for r in records:
        out.setdefault(r.get(key), []).append(r)
    return out


def workflow_lifecycle_integrity() -> dict:
    """워크플로 생애주기 전이 합법성(순차, DRAFT 시작)."""
    issues: list = []
    for wid, evs in sorted(_group(ledger.read_workflow_events(), "workflow_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != W_DRAFT:
                    issues.append(f"bad_initial_wf:{wid}:{to}")
            elif not can_workflow_transition(prev, to):
                issues.append(f"invalid_wf_transition:{wid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def task_lifecycle_integrity() -> dict:
    """작업 생애주기 전이 합법성(순차, CREATED 시작)."""
    issues: list = []
    for tid, evs in sorted(_group(ledger.read_task_events(), "task_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_status")
            if prev is None:
                if to != T_CREATED:
                    issues.append(f"bad_initial_task:{tid}:{to}")
            elif not can_task_transition(prev, to):
                issues.append(f"invalid_task_transition:{tid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 워크플로/작업: genesis 이벤트 유일."""
    issues: list = []
    wf_seen: set = set()
    for ev in ledger.read_workflow_events():
        if ev.get("from_state") == GENESIS:
            wid = ev.get("workflow_id")
            if wid in wf_seen:
                issues.append(f"duplicate_workflow:{wid}")
            wf_seen.add(wid)
    t_seen: set = set()
    for ev in ledger.read_task_events():
        if ev.get("from_status") == GENESIS:
            tid = ev.get("task_id")
            if tid in t_seen:
                issues.append(f"duplicate_task:{tid}")
            t_seen.add(tid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def dependency_integrity() -> dict:
    """의존 그래프: depends_on 이 존재 작업 참조(dangling) + 순환(DAG 위반)."""
    issues: list = []
    tids = {r.get("task_id") for r in ledger.read_task_events()}
    edges: list = []
    for d in ledger.read_dependencies():
        t, dep = d.get("task_id"), d.get("depends_on")
        if t not in tids:
            issues.append(f"orphan_dependency_task:{d.get('dependency_id')}")
        if dep not in tids:
            issues.append(f"dangling_dependency:{d.get('dependency_id')}")
        edges.append((t, dep))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("circular_dependency:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 작업/의존/런의 workflow_id 가 존재하는지."""
    issues: list = []
    wids = set(ledger.workflow_ids())
    for ev in ledger.read_task_events():
        if ev.get("from_status") == GENESIS and ev.get("workflow_id") not in wids:
            issues.append(f"orphan_task_workflow:{ev.get('task_id')}")
    for d in ledger.read_dependencies():
        if d.get("workflow_id") not in wids:
            issues.append(f"orphan_dependency_workflow:{d.get('dependency_id')}")
    for r in ledger.read_runs():
        if r.get("workflow_id") not in wids:
            issues.append(f"orphan_run:{r.get('run_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): dangling·순환."""
    issues: list = []
    arts = ledger.read_artifacts()
    aids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in aids:
                issues.append(f"dangling_artifact:{a.get('artifact_id')}")
            edges.append((a.get("artifact_id"), parent))
    if detect_cycle(edges):
        issues.append("cycle_artifact")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    wf_life = workflow_lifecycle_integrity()
    task_life = task_lifecycle_integrity()
    duplicate = duplicate_integrity()
    dependency = dependency_integrity()
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = (ok and wf_life["ok"] and task_life["ok"] and duplicate["ok"] and dependency["ok"]
          and reference["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "workflow_lifecycle": wf_life,
            "task_lifecycle": task_life, "duplicate": duplicate, "dependency": dependency,
            "reference": reference, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "workflow_event_count": r1.workflow_event_count, "task_event_count": r1.task_event_count}
