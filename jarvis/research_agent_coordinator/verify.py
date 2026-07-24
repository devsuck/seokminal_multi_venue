"""Research Agent Coordinator 검증 (P12.3) — 체인·변조·중복·생애주기·상충소유·핸드오프증거·완료결과·고아·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 배정 생애주기 전이 합법성(CREATED 시작). 상충
소유(한 작업 활성 소유자 유일). 핸드오프 증거 무결성(evidence_ref 필수). 완료 결과 무결성(COMPLETED 이벤트 result_ref).
고아(진행/핸드오프의 배정 존재·로스터). **변경/실행 없음.**
"""
from __future__ import annotations

from jarvis.research_agent_coordinator import ledger
from jarvis.research_agent_coordinator.models import (
    A_COMPLETED,
    A_CREATED,
    ACTIVE_STATES,
    GENESIS,
    can_transition,
    content_hash,
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


def _by_assignment() -> dict:
    out: dict = {}
    for ev in ledger.read_ownership_events():
        out.setdefault(ev.get("assignment_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """배정 생애주기 전이 합법성(순차, CREATED 시작)."""
    issues: list = []
    for aid, evs in sorted(_by_assignment().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != A_CREATED:
                    issues.append(f"bad_initial:{aid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{aid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def ownership_integrity() -> dict:
    """상충 소유: 각 작업(task_ref)의 활성 배정은 소유자가 하나여야 한다."""
    issues: list = []
    by_task: dict = {}
    meta = _by_assignment()
    for aid, evs in meta.items():
        g, last = evs[0], evs[-1]
        by_task.setdefault(g.get("task_ref"), []).append((aid, last.get("to_state"),
                                                           last.get("agent")))
    for task, lst in sorted(by_task.items()):
        active_owners = {agent for _, st, agent in lst if st in ACTIVE_STATES}
        if len(active_owners) > 1:
            issues.append(f"conflicting_owner:{task}:{sorted(active_owners)}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def handoff_integrity() -> dict:
    """핸드오프 증거 무결성: 모든 핸드오프는 evidence_ref 를 가진다."""
    issues: list = []
    aids = set(ledger.assignment_ids())
    for h in ledger.read_handoffs():
        if not h.get("evidence_ref"):
            issues.append(f"handoff_no_evidence:{h.get('handoff_id')}")
        if h.get("assignment_id") not in aids:
            issues.append(f"orphan_handoff:{h.get('handoff_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def completion_integrity() -> dict:
    """완료 결과 무결성: COMPLETED 이벤트는 result_ref 를 가진다."""
    issues: list = []
    for ev in ledger.read_ownership_events():
        if ev.get("to_state") == A_COMPLETED and not ev.get("result_ref"):
            issues.append(f"completion_no_result:{ev.get('assignment_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def orphan_integrity() -> dict:
    """고아: 진행/핸드오프의 배정 존재, 배정 소유 에이전트의 로스터 등록."""
    issues: list = []
    aids = set(ledger.assignment_ids())
    for p in ledger.read_progress():
        if p.get("assignment_id") not in aids:
            issues.append(f"orphan_progress:{p.get('progress_id')}")
    rostered = {(r.get("coordinator"), r.get("agent")) for r in ledger.read_agents()}
    for aid, evs in _by_assignment().items():
        g = evs[0]
        if (g.get("coordinator"), g.get("agent")) not in rostered:
            issues.append(f"unrostered_agent:{aid}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lifecycle = lifecycle_integrity()
    ownership = ownership_integrity()
    handoff = handoff_integrity()
    completion = completion_integrity()
    orphan = orphan_integrity()
    ok = (ok and lifecycle["ok"] and ownership["ok"] and handoff["ok"] and completion["ok"]
          and orphan["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "ownership": ownership, "handoff": handoff, "completion": completion, "orphan": orphan}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "ownership_event_count": r1.ownership_event_count,
            "handoff_count": r1.handoff_count}
