"""Research Coordinator 검증 (P11.7) — 체인·변조·중복·플랜/태스크 생애주기·DAG·계보·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 플랜/태스크 전이 합법성. 의존성 DAG(순환 없음).
아티팩트 계보 dangling·순환. **변경/실행/거래/배포 없음.**
"""
from __future__ import annotations

from jarvis.research_coordinator import ledger
from jarvis.research_coordinator.models import (
    GENESIS,
    P_CREATED,
    T_ASSIGNED,
    can_transition_plan,
    can_transition_task,
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


def plan_lifecycle_integrity() -> dict:
    """플랜별 생애주기 전이 합법성(순차)."""
    issues: list = []
    by_plan: dict = {}
    for ev in ledger.read_plan_events():
        by_plan.setdefault(ev.get("plan_id"), []).append(ev)
    for pid, evs in sorted(by_plan.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != P_CREATED:
                    issues.append(f"bad_initial:{pid}:{to}")
            elif not can_transition_plan(prev, to):
                issues.append(f"illegal:{pid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def task_lifecycle_integrity() -> dict:
    """태스크별 배정 이벤트 전이 합법성(재분배는 ASSIGNED 리셋 허용)."""
    issues: list = []
    by_task: dict = {}
    for ev in ledger.read_assignments():
        by_task.setdefault(ev.get("task_id"), []).append(ev)
    for tid, evs in sorted(by_task.items()):
        prev = None
        for ev in evs:
            to = ev.get("state")
            if prev is None:
                if to != T_ASSIGNED:
                    issues.append(f"bad_initial:{tid}:{to}")
            elif ev.get("is_reassignment"):
                if to != T_ASSIGNED:
                    issues.append(f"bad_reassign:{tid}:{to}")
            elif to != prev and not can_transition_task(prev, to):
                issues.append(f"illegal:{tid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def dag_integrity() -> dict:
    """모든 플랜의 의존성 그래프가 DAG(순환 없음)."""
    issues: list = []
    for plan in ledger.plan_ids():
        edges = [(d.get("upstream_task"), d.get("downstream_task"))
                 for d in ledger.plan_dependencies(plan)]
        cyc = detect_cycle(edges)
        if cyc:
            issues.append(f"cycle:{plan}:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): dangling·순환."""
    issues: list = []
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"dangling:{a.get('artifact_id')}->{parent}")
            edges.append((a.get("artifact_id"), parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("lineage_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    plan_lc = plan_lifecycle_integrity()
    task_lc = task_lifecycle_integrity()
    dag = dag_integrity()
    lineage = lineage_integrity()
    ok = ok and plan_lc["ok"] and task_lc["ok"] and dag["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "plan_lifecycle": plan_lc,
            "task_lifecycle": task_lc, "dag": dag, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "coordinator_count": r1.coordinator_count,
            "assignment_event_count": r1.assignment_event_count,
            "escalation_count": r1.escalation_count}
