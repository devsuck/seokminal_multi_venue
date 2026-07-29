"""Experiment Orchestration 검증 (P31) — 체인·중복·계획/요청 생애주기·실행금지·의존성 순환·승인·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계획/요청 생애주기(DRAFT/REQUESTED 시작). 중복
genesis 유일. 실행 방지(모든 요청 is_executed=False). 의존성 순환 없음. 승인 무결성(APPROVED/REJECTED approver 존재).
아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.experiment_orchestration import ledger
from jarvis.experiment_orchestration import models as M
from jarvis.experiment_orchestration.models import GENESIS, content_hash, detect_cycle_check


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


def plan_lifecycle_integrity() -> dict:
    issues: list = []
    for pid, evs in sorted(_group(ledger.read_plan_events(), "plan_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.P_DRAFT:
                    issues.append(f"bad_initial:{pid}:{to}")
            elif not M.can_plan_transition(prev, to):
                issues.append(f"invalid_transition:{pid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def request_lifecycle_integrity() -> dict:
    issues: list = []
    for rid, evs in sorted(_group(ledger.read_request_events(), "request_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.R_REQUESTED:
                    issues.append(f"bad_initial:{rid}:{to}")
            elif not M.can_request_transition(prev, to):
                issues.append(f"invalid_transition:{rid}:{prev}->{to}")
            if to in (M.R_APPROVED, M.R_REJECTED) and not ev.get("approver"):
                issues.append(f"no_approver:{rid}:{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def execution_prevention_integrity() -> dict:
    """실행 방지: 모든 실행 요청 이벤트 is_executed=False(조정만·실험 실행 금지)."""
    issues: list = []
    for ev in ledger.read_request_events():
        if ev.get("is_executed") is not False:
            issues.append(f"executed_request:{ev.get('request_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def dependency_integrity() -> dict:
    """의존성 무결성: 순환 없음 + 유형 유효 + 알려진 계획 참조."""
    issues: list = []
    plan_ids = set(ledger.plan_ids())
    for d in ledger.read_dependencies():
        if d.get("dependency_type") not in M.DEPENDENCY_TYPES:
            issues.append(f"invalid_dependency_type:{d.get('dependency_id')}")
        if d.get("plan_id") not in plan_ids or d.get("depends_on") not in plan_ids:
            issues.append(f"orphan_dependency:{d.get('dependency_id')}")
    if detect_cycle_check(ledger.all_dependency_edges()):
        issues.append("cycle_dependency")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    for records, key, glabel in ((ledger.read_plan_events(), "plan_id", "plan"),
                                 (ledger.read_request_events(), "request_id", "request")):
        seen: set = set()
        for ev in records:
            if ev.get("from_state") == GENESIS:
                gid = ev.get(key)
                if gid in seen:
                    issues.append(f"duplicate_{glabel}:{gid}")
                seen.add(gid)
    s2: set = set()
    for r in ledger.read_reports():
        rid = r.get("report_id")
        if rid in s2:
            issues.append(f"duplicate_report:{rid}")
        s2.add(rid)
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
    plan = plan_lifecycle_integrity()
    request = request_lifecycle_integrity()
    execution = execution_prevention_integrity()
    dependency = dependency_integrity()
    duplicate = duplicate_integrity()
    lineage = lineage_integrity()
    ok = (ok and plan["ok"] and request["ok"] and execution["ok"] and dependency["ok"]
          and duplicate["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "plan_lifecycle": plan,
            "request_lifecycle": request, "execution_prevention": execution,
            "dependency": dependency, "duplicate": duplicate, "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "plan_count": r1.plan_count, "request_count": r1.request_count}
