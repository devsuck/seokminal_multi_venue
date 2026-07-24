"""Autonomous Research 검증 (P25) — 체인·중복·사이클/제안 생애주기·기회(자동선택 금지)·계획(실행 금지)·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 사이클 생애주기(CREATED 시작). 제안 생애주기
(DRAFT 시작). 중복 사이클/제안(genesis 유일). 기회 무결성(is_auto_selected=False). 계획 무결성(is_executable=False).
아티팩트 계보(missing parent·broken reference·순환). **변경 없음.**
"""
from __future__ import annotations

from jarvis.autonomous_research import ledger
from jarvis.autonomous_research import models as M
from jarvis.autonomous_research.models import GENESIS, content_hash, detect_cycle_check


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


def cycle_lifecycle_integrity() -> dict:
    """사이클 생애주기 전이 합법성(CREATED 시작)."""
    issues: list = []
    for cid, evs in sorted(_group(ledger.read_cycle_events(), "cycle_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.C_CREATED:
                    issues.append(f"bad_initial:{cid}:{to}")
            elif not M.can_cycle_transition(prev, to):
                issues.append(f"invalid_transition:{cid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def proposal_lifecycle_integrity() -> dict:
    """제안 생애주기 전이 합법성(DRAFT 시작)."""
    issues: list = []
    for pid, evs in sorted(_group(ledger.read_proposal_events(), "proposal_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.P_DRAFT:
                    issues.append(f"bad_initial:{pid}:{to}")
            elif not M.can_proposal_transition(prev, to):
                issues.append(f"invalid_transition:{pid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 방지: 사이클/제안 genesis 유일 + 리포트 id 유일."""
    issues: list = []
    for records, key, glabel in ((ledger.read_cycle_events(), "cycle_id", "cycle"),
                                 (ledger.read_proposal_events(), "proposal_id", "proposal")):
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


def opportunity_integrity() -> dict:
    """기회 무결성: 모든 기회 is_auto_selected=False(점수만·자동 선택 금지) + 패턴 유효."""
    issues: list = []
    for o in ledger.read_opportunities():
        if o.get("is_auto_selected") is not False:
            issues.append(f"auto_selected_opportunity:{o.get('opportunity_id')}")
        if o.get("source_pattern") not in M.OPPORTUNITY_PATTERNS:
            issues.append(f"invalid_pattern:{o.get('opportunity_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def plan_integrity() -> dict:
    """계획 무결성: 모든 실험 계획 is_executable=False(계획만·실행 금지) + 알려진 제안 참조."""
    issues: list = []
    prop_ids = set(ledger.proposal_ids())
    for p in ledger.read_experiment_plans():
        if p.get("is_executable") is not False:
            issues.append(f"executable_plan:{p.get('plan_id')}")
        if p.get("proposal_id") not in prop_ids:
            issues.append(f"orphan_plan:{p.get('plan_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def learning_integrity() -> dict:
    """학습 무결성: 학습 종류 유효."""
    issues: list = []
    for le in ledger.read_learning_events():
        if le.get("kind") not in M.LEARNING_KINDS:
            issues.append(f"invalid_learning_kind:{le.get('learning_event_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): missing parent·broken reference·순환. Failure→Opportunity→Proposal→Plan→Feedback."""
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
    cycle = cycle_lifecycle_integrity()
    proposal = proposal_lifecycle_integrity()
    duplicate = duplicate_integrity()
    opportunity = opportunity_integrity()
    plan = plan_integrity()
    learning = learning_integrity()
    lineage = lineage_integrity()
    ok = (ok and cycle["ok"] and proposal["ok"] and duplicate["ok"] and opportunity["ok"]
          and plan["ok"] and learning["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "cycle_lifecycle": cycle,
            "proposal_lifecycle": proposal, "duplicate": duplicate, "opportunity": opportunity,
            "plan": plan, "learning": learning, "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약/리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "cycle_count": r1.cycle_count, "proposal_count": r1.proposal_count}
