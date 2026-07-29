"""Research Agents 검증 (P11.1) — 체인·변조·중복·태스크 생애주기·권한 경계·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 태스크: 전이 합법성. 권한 경계: 활동 감사에
금지 행위(TRADE/EXECUTE/DEPLOY/ALLOCATE)가 allowed=True 로 기록되지 않음. **변경/실행/거래/배포/할당 없음.**
"""
from __future__ import annotations

from jarvis.research_agents import ledger
from jarvis.research_agents.models import (
    ACT_KIND_BLOCKED,
    GENESIS,
    TASK_CREATED,
    can_transition_task,
    content_hash,
    is_forbidden_action,
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


def task_lifecycle_integrity() -> dict:
    """태스크별 전이 합법성(순차) 검증."""
    issues: list = []
    by_task: dict = {}
    for ev in ledger.read_tasks():
        by_task.setdefault(ev.get("task_id"), []).append(ev)
    for task, evs in sorted(by_task.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != TASK_CREATED:
                    issues.append(f"bad_initial:{task}:{to}")
            elif not can_transition_task(prev, to):
                issues.append(f"illegal_transition:{task}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def permission_boundary() -> dict:
    """권한 경계: 금지 행위가 allowed=True 로 기록되지 않음(에이전트는 연구 보조만)."""
    issues: list = []
    for a in ledger.read_activity():
        if is_forbidden_action(a.get("action", "")) and a.get("allowed", False):
            issues.append(f"forbidden_allowed:{a.get('activity_id')}")
        if a.get("kind") == ACT_KIND_BLOCKED and a.get("allowed", False):
            issues.append(f"blocked_marked_allowed:{a.get('activity_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    task = task_lifecycle_integrity()
    perm = permission_boundary()
    ok = ok and task["ok"] and perm["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "task_lifecycle": task, "permission": perm}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "agent_count": r1.agent_count, "activity_count": r1.activity_count,
            "blocked_count": r1.blocked_count}
