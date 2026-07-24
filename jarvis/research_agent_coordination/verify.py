"""Research Agent Coordination 검증 (P26) — 체인·중복·세션/작업 생애주기·역할 분리·합의(자동결정 금지)·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 세션 생애주기(CREATED 시작). 작업 생애주기(CREATED
시작). 중복 세션/작업(genesis 유일). 역할 분리(allowed_actions 금지 동사 없음). 합의 무결성(is_decision=False·판정 유효).
작업 격리(owner·objective). 아티팩트 계보(missing parent·broken reference·순환). **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_agent_coordination import ledger
from jarvis.research_agent_coordination import models as M
from jarvis.research_agent_coordination.models import GENESIS, content_hash, detect_cycle_check


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


def session_lifecycle_integrity() -> dict:
    """세션 생애주기 전이 합법성(CREATED 시작)."""
    issues: list = []
    for sid, evs in sorted(_group(ledger.read_session_events(), "session_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.S_CREATED:
                    issues.append(f"bad_initial:{sid}:{to}")
            elif not M.can_session_transition(prev, to):
                issues.append(f"invalid_transition:{sid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def task_lifecycle_integrity() -> dict:
    """작업 생애주기 전이 합법성(CREATED 시작) + 작업 격리(owner·objective)."""
    issues: list = []
    for tid, evs in sorted(_group(ledger.read_task_events(), "task_id").items()):
        prev = None
        g = evs[0]
        if not g.get("assigned_agent"):
            issues.append(f"no_owner:{tid}")
        if not g.get("objective"):
            issues.append(f"no_objective:{tid}")
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.T_CREATED:
                    issues.append(f"bad_initial:{tid}:{to}")
            elif not M.can_task_transition(prev, to):
                issues.append(f"invalid_transition:{tid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 방지: 세션/작업 genesis 유일 + 에이전트/역할/팀/리포트 id 유일."""
    issues: list = []
    for records, key, glabel in ((ledger.read_session_events(), "session_id", "session"),
                                 (ledger.read_task_events(), "task_id", "task")):
        seen: set = set()
        for ev in records:
            if ev.get("from_state") == GENESIS:
                gid = ev.get(key)
                if gid in seen:
                    issues.append(f"duplicate_{glabel}:{gid}")
                seen.add(gid)
    for records, idf, label in ((ledger.read_agents(), "agent_id", "agent"),
                                (ledger.read_roles(), "role_id", "role"),
                                (ledger.read_teams(), "team_id", "team"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def role_separation_integrity() -> dict:
    """역할 분리: allowed_actions 에 금지 동사(실행/배포/승인/권한변경) 없음 + 작업 objective 금지 동사 없음."""
    issues: list = []
    for r in ledger.read_roles():
        if M.contains_forbidden_action(r.get("allowed_actions", [])):
            issues.append(f"forbidden_role_action:{r.get('role_id')}")
    for ev in ledger.read_task_events():
        if M.is_forbidden_verb(ev.get("objective")):
            issues.append(f"forbidden_task_objective:{ev.get('task_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def consensus_integrity() -> dict:
    """합의 무결성: 모든 합의 is_decision=False(기록만·자동 결정 금지) + 판정 유효."""
    issues: list = []
    for c in ledger.read_consensus():
        if c.get("is_decision") is not False:
            issues.append(f"decision_consensus:{c.get('consensus_id')}")
        if c.get("verdict") not in M.CONSENSUS_VERDICTS:
            issues.append(f"invalid_verdict:{c.get('consensus_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): missing parent·broken reference·순환. Agent→Task→Message→Consensus."""
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
    session = session_lifecycle_integrity()
    task = task_lifecycle_integrity()
    duplicate = duplicate_integrity()
    role = role_separation_integrity()
    consensus = consensus_integrity()
    lineage = lineage_integrity()
    ok = (ok and session["ok"] and task["ok"] and duplicate["ok"] and role["ok"]
          and consensus["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "session_lifecycle": session,
            "task_lifecycle": task, "duplicate": duplicate, "role_separation": role,
            "consensus": consensus, "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약/리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "agent_count": r1.agent_count, "consensus_count": r1.consensus_count}
