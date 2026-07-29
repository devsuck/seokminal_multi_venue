"""Autonomous Experiment Scheduler 검증 (P12.2) — 체인·변조·중복·생애주기·의존(순환/dangling)·고아·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 요청 생애주기 전이 합법성(REQUESTED 시작).
중복 실행 요청(genesis 유일). 의존 그래프 순환/dangling. 고아 요청(스케줄 부재). **변경/실행 없음.**
"""
from __future__ import annotations

from jarvis.autonomous_experiment_scheduler import ledger
from jarvis.autonomous_experiment_scheduler.models import (
    GENESIS,
    Q_REQUESTED,
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


def lifecycle_integrity() -> dict:
    """요청 생애주기 전이 합법성(순차, REQUESTED 시작)."""
    issues: list = []
    by_req: dict = {}
    for ev in ledger.read_schedule_events():
        by_req.setdefault(ev.get("request_id"), []).append(ev)
    for req, evs in sorted(by_req.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != Q_REQUESTED:
                    issues.append(f"bad_initial:{req}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{req}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 실행 요청: 같은 request_id 의 REQUESTED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_schedule_events():
        if ev.get("from_state") == GENESIS:
            req = ev.get("request_id")
            if req in genesis_seen:
                issues.append(f"duplicate_request:{req}")
            genesis_seen.add(req)
    return {"ok": not issues, "issues": sorted(set(issues))}


def dependency_integrity() -> dict:
    """의존 그래프: depends_on 이 존재 요청 참조(dangling) + 순환(circular scheduling)."""
    issues: list = []
    reqs = set(ledger.request_ids())
    edges: list = []
    for d in ledger.read_dependencies():
        r, dep = d.get("request_id"), d.get("depends_on")
        if r not in reqs:
            issues.append(f"orphan_dependency_request:{d.get('dependency_id')}")
        if dep not in reqs:
            issues.append(f"dangling_dependency:{d.get('dependency_id')}")
        edges.append((r, dep))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("circular_scheduling:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def orphan_integrity() -> dict:
    """고아 요청: 이벤트/우선순위/의존의 schedule 이 존재하는지, 요청 존재하는지."""
    issues: list = []
    sids = {s.get("schedule_id") for s in ledger.read_schedules()}
    reqs = set(ledger.request_ids())
    for ev in ledger.read_schedule_events():
        if ev.get("from_state") == GENESIS and ev.get("schedule_id") not in sids:
            issues.append(f"orphan_request_schedule:{ev.get('request_id')}")
    for p in ledger.read_priorities():
        if p.get("request_id") not in reqs:
            issues.append(f"orphan_priority:{p.get('priority_id')}")
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
    orphan = orphan_integrity()
    ok = ok and lifecycle["ok"] and duplicate["ok"] and dependency["ok"] and orphan["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "dependency": dependency, "orphan": orphan}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "schedule_event_count": r1.schedule_event_count,
            "dependency_count": r1.dependency_count}
