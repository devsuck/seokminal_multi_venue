"""Research Task Planner 검증 (P11.2) — 체인·변조·중복·DAG·계보·계획 생애주기·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계획별 태스크 그래프가 DAG(순환 없음)이며
태스크 계보에 dangling/순환 없음. 계획 생애주기 전이 합법성. **변경/실행/자동승인/자동배포 없음.**
"""
from __future__ import annotations

from jarvis.research_task_planner import ledger
from jarvis.research_task_planner.models import (
    GENESIS,
    PLAN_REQUESTED,
    can_transition_plan,
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


def dag_integrity() -> dict:
    """모든 계획의 태스크 그래프가 DAG(순환 없음)인지 검증."""
    issues: list = []
    for plan in ledger.plan_ids():
        edges = [(d.get("upstream_task"), d.get("downstream_task"))
                 for d in ledger.plan_dependencies(plan)]
        cyc = detect_cycle(edges)
        if cyc:
            issues.append(f"cycle:{plan}:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """모든 계획의 태스크 계보(parent) 무결성: dangling·순환."""
    issues: list = []
    for plan in ledger.plan_ids():
        tasks = ledger.plan_tasks(plan)
        ids = {t.get("task_id") for t in tasks}
        pm = {t.get("task_id"): t.get("parent_task") for t in tasks if t.get("parent_task")}
        for tid, parent in sorted(pm.items()):
            if parent not in ids:
                issues.append(f"dangling:{plan}:{tid}->{parent}")
        cyc = detect_cycle(list(pm.items()))
        if cyc:
            issues.append(f"lineage_cycle:{plan}:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def lifecycle_integrity() -> dict:
    """계획별 생애주기 전이 합법성(순차)."""
    issues: list = []
    by_plan: dict = {}
    for ev in ledger.read_plan_events():
        by_plan.setdefault(ev.get("plan_id"), []).append(ev)
    for plan, evs in sorted(by_plan.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != PLAN_REQUESTED:
                    issues.append(f"bad_initial:{plan}:{to}")
            elif not can_transition_plan(prev, to):
                issues.append(f"illegal:{plan}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    dag = dag_integrity()
    lineage = lineage_integrity()
    lifecycle = lifecycle_integrity()
    ok = ok and dag["ok"] and lineage["ok"] and lifecycle["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "dag": dag, "lineage": lineage,
            "lifecycle": lifecycle}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "task_count": r1.task_count, "dependency_count": r1.dependency_count,
            "schedule_count": r1.schedule_count}
