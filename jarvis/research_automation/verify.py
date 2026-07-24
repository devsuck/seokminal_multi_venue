"""Research Automation 검증 (P22) — 체인·중복·생애주기(3종)·의존(DAG)·참조·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 워크플로/파이프라인/작업 생애주기 전이 합법성
(genesis 시작). 의존 그래프(dangling·순환). 참조 무결성(파이프라인/작업/런→상위). 계보(dangling·순환). **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_automation import ledger
from jarvis.research_automation import models as M
from jarvis.research_automation.models import GENESIS, content_hash, detect_cycle


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


def _lifecycle(records, gkey, initial, can_fn) -> dict:
    issues: list = []
    for gid, evs in sorted(_group(records, gkey).items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != initial:
                    issues.append(f"bad_initial:{gid}:{to}")
            elif not can_fn(prev, to):
                issues.append(f"invalid_transition:{gid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def lifecycle_integrity() -> dict:
    checks = {
        "workflow": _lifecycle(ledger.read_workflow_events(), "workflow_id", M.W_DRAFT,
                               M.can_workflow_transition),
        "pipeline": _lifecycle(ledger.read_pipeline_events(), "pipeline_id", M.P_CREATED,
                               M.can_pipeline_transition),
        "task": _lifecycle(ledger.read_task_events(), "task_id", M.T_CREATED, M.can_task_transition),
    }
    return {"ok": all(v["ok"] for v in checks.values()), "checks": checks}


def duplicate_integrity() -> dict:
    """중복 워크플로/파이프라인/작업: genesis 이벤트 유일 + 런 id 유일(중복 실행 방지)."""
    issues: list = []
    for records, id_key, from_key in (
            (ledger.read_workflow_events(), "workflow_id", "from_state"),
            (ledger.read_pipeline_events(), "pipeline_id", "from_state"),
            (ledger.read_task_events(), "task_id", "from_state")):
        seen: set = set()
        for ev in records:
            if ev.get(from_key) == GENESIS:
                gid = ev.get(id_key)
                if gid in seen:
                    issues.append(f"duplicate:{id_key}:{gid}")
                seen.add(gid)
    rseen: set = set()
    for r in ledger.read_runs():
        rid = r.get("run_id")
        if rid in rseen:
            issues.append(f"duplicate_run:{rid}")
        rseen.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def dependency_integrity() -> dict:
    """의존 그래프: parent/child 가 존재 작업 참조(dangling·missing) + 순환(DAG 위반)."""
    issues: list = []
    tids = {r.get("task_id") for r in ledger.read_task_events()}
    edges: list = []
    for d in ledger.read_dependencies():
        p, c = d.get("parent_task"), d.get("child_task")
        if p not in tids:
            issues.append(f"missing_dependency_parent:{d.get('dependency_id')}")
        if c not in tids:
            issues.append(f"missing_dependency_child:{d.get('dependency_id')}")
        edges.append((c, p))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("circular_dependency:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 파이프라인→워크플로, 작업→파이프라인, 런→파이프라인."""
    issues: list = []
    wids = set(ledger.workflow_ids())
    pids = {ev.get("pipeline_id") for ev in ledger.read_pipeline_events()}
    for ev in ledger.read_pipeline_events():
        if ev.get("from_state") == GENESIS and ev.get("workflow_id") not in wids:
            issues.append(f"orphan_pipeline:{ev.get('pipeline_id')}")
    for ev in ledger.read_task_events():
        if ev.get("from_state") == GENESIS and ev.get("pipeline_id") not in pids:
            issues.append(f"orphan_task:{ev.get('task_id')}")
    for r in ledger.read_runs():
        if r.get("pipeline_id") not in pids:
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
    lifecycle = lifecycle_integrity()
    duplicate = duplicate_integrity()
    dependency = dependency_integrity()
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and dependency["ok"] and reference["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "dependency": dependency, "reference": reference,
            "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "workflow_event_count": r1.workflow_event_count, "task_event_count": r1.task_event_count}
