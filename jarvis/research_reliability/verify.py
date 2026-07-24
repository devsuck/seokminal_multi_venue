"""Research Reliability 검증 (P24) — 체인·중복·장애/포스트모템 생애주기·복구·무결성·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 장애 생애주기 전이 합법성(OPEN 시작). 포스트모템
생애주기(DRAFT 시작). 중복 장애/포스트모템(genesis 유일). 복구 무결성(계획 auto_execute=False·result 유효). 지표
관찰성(is_observation=True). 아티팩트 계보(missing parent·broken reference·순환). **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_reliability import ledger
from jarvis.research_reliability import models as M
from jarvis.research_reliability.models import GENESIS, content_hash, detect_cycle_check


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


def incident_lifecycle_integrity() -> dict:
    """장애 생애주기 전이 합법성(OPEN 시작)."""
    issues: list = []
    for iid, evs in sorted(_group(ledger.read_incident_events(), "incident_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.I_OPEN:
                    issues.append(f"bad_initial:{iid}:{to}")
            elif not M.can_incident_transition(prev, to):
                issues.append(f"invalid_transition:{iid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def postmortem_lifecycle_integrity() -> dict:
    """포스트모템 생애주기 전이 합법성(DRAFT 시작)."""
    issues: list = []
    for pid, evs in sorted(_group(ledger.read_postmortem_events(), "postmortem_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.P_DRAFT:
                    issues.append(f"bad_initial:{pid}:{to}")
            elif not M.can_postmortem_transition(prev, to):
                issues.append(f"invalid_transition:{pid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 방지: 장애/포스트모템 genesis 유일 + 리포트 id 유일."""
    issues: list = []
    for records, key, glabel in ((ledger.read_incident_events(), "incident_id", "incident"),
                                 (ledger.read_postmortem_events(), "postmortem_id", "postmortem")):
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


def recovery_integrity() -> dict:
    """복구 무결성: 계획 auto_execute=False·복구 결과 유효·계획/이벤트가 알려진 장애 참조."""
    issues: list = []
    inc_ids = set(ledger.incident_ids())
    for p in ledger.read_recovery_plans():
        if p.get("auto_execute") is not False:
            issues.append(f"auto_execute_plan:{p.get('plan_id')}")
        if p.get("incident_id") not in inc_ids:
            issues.append(f"orphan_plan:{p.get('plan_id')}")
    for ev in ledger.read_recovery_events():
        if ev.get("result") not in M.RECOVERY_RESULTS:
            issues.append(f"invalid_recovery_result:{ev.get('event_id')}")
        if ev.get("incident_id") not in inc_ids:
            issues.append(f"orphan_recovery_event:{ev.get('event_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def metric_integrity() -> dict:
    """지표 무결성: 모든 신뢰성 지표 is_observation=True(관찰만, 자동 결정 금지) + 이름 유효."""
    issues: list = []
    for m in ledger.read_reliability_metrics():
        if m.get("is_observation") is not True:
            issues.append(f"non_observation_metric:{m.get('metric_id')}")
        if m.get("metric_name") not in M.RELIABILITY_METRICS:
            issues.append(f"unknown_metric:{m.get('metric_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def check_integrity() -> dict:
    """무결성 검사 무결성: type·result 유효."""
    issues: list = []
    for c in ledger.read_integrity_checks():
        if c.get("check_type") not in M.INTEGRITY_CHECK_TYPES:
            issues.append(f"invalid_check_type:{c.get('check_id')}")
        if c.get("result") not in M.CHECK_RESULTS:
            issues.append(f"invalid_check_result:{c.get('check_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): missing parent·broken reference·순환."""
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
    incident = incident_lifecycle_integrity()
    postmortem = postmortem_lifecycle_integrity()
    duplicate = duplicate_integrity()
    recovery = recovery_integrity()
    metric = metric_integrity()
    check = check_integrity()
    lineage = lineage_integrity()
    ok = (ok and incident["ok"] and postmortem["ok"] and duplicate["ok"] and recovery["ok"]
          and metric["ok"] and check["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "incident_lifecycle": incident,
            "postmortem_lifecycle": postmortem, "duplicate": duplicate, "recovery": recovery,
            "metric": metric, "check": check, "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약/지표 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    m1 = engine.calculate_reliability_metrics(now, commit=False)
    m2 = engine.calculate_reliability_metrics(now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and m1 == m2,
            "incident_count": r1.incident_count, "metric_count": r1.reliability_metric_count}
