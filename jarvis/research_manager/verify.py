"""Autonomous Research Manager 검증 (P12.9) — 체인·변조·중복·생애주기·의존·참조·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계획 생애주기 전이 합법성(CREATED 시작). 중복
계획(genesis 유일). 의존 그래프(순환/dangling). 참조 무결성(작업/의존/진행의 계획·작업). 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_manager import ledger
from jarvis.research_manager.models import (
    P_CREATED,
    GENESIS,
    can_transition,
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


def _by_plan() -> dict:
    out: dict = {}
    for ev in ledger.read_plan_events():
        out.setdefault(ev.get("plan_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """계획 생애주기 전이 합법성(순차, CREATED 시작)."""
    issues: list = []
    for pid, evs in sorted(_by_plan().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != P_CREATED:
                    issues.append(f"bad_initial:{pid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{pid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 계획: 같은 plan_id 의 CREATED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_plan_events():
        if ev.get("from_state") == GENESIS:
            pid = ev.get("plan_id")
            if pid in genesis_seen:
                issues.append(f"duplicate_plan:{pid}")
            genesis_seen.add(pid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def dependency_integrity() -> dict:
    """의존 그래프: depends_on 이 존재 작업 참조(dangling) + 순환."""
    issues: list = []
    tids = {t.get("task_id") for t in ledger.read_tasks()}
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
    """참조 무결성: 작업의 계획, 진행의 작업/계획이 존재하는지."""
    issues: list = []
    pids = set(ledger.plan_ids())
    tids = {t.get("task_id") for t in ledger.read_tasks()}
    for t in ledger.read_tasks():
        if t.get("plan_id") not in pids:
            issues.append(f"orphan_task_plan:{t.get('task_id')}")
    for p in ledger.read_progress():
        if p.get("task_id") not in tids:
            issues.append(f"orphan_progress_task:{p.get('progress_id')}")
        if p.get("plan_id") not in pids:
            issues.append(f"orphan_progress_plan:{p.get('progress_id')}")
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
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("cycle_artifact:" + "->".join(cyc))
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


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "plan_event_count": r1.plan_event_count, "task_count": r1.task_count}
