"""Autonomous Research Organization 검증 (P11.13) — 체인·변조·중복·생애주기·소유·역할·책임·의존·계보·스냅샷. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 조직 생애주기 전이 합법성(CREATED 시작·
unauthorized transition 탐지). 소유 무결성(워크플로 owner 유닛 존재·책임 owner). 역할 무결성(orphan agent·중복 역할).
책임 체인(input_sources 참조). 의존 순환(circular dependency). 계보 dangling·순환. 스냅샷 일관성. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_organization import ledger
from jarvis.research_organization.models import (
    GENESIS,
    O_CREATED,
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
    """조직별 생애주기 전이 합법성(순차, CREATED 시작) — unauthorized transition 탐지."""
    issues: list = []
    by_org: dict = {}
    for ev in ledger.read_org_events():
        by_org.setdefault(ev.get("org_id"), []).append(ev)
    for org, evs in sorted(by_org.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != O_CREATED:
                    issues.append(f"bad_initial:{org}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"unauthorized_transition:{org}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def ownership_integrity() -> dict:
    """소유 무결성: 워크플로 owner 유닛 존재, 책임 owner 비어있지 않음(invalid ownership)."""
    issues: list = []
    uids = {u.get("unit_id") for u in ledger.read_units()}
    for w in ledger.read_workflows():
        ow = w.get("owner_unit")
        if ow and ow not in uids:
            issues.append(f"invalid_workflow_owner:{w.get('workflow_id')}")
    for r in ledger.read_responsibilities():
        if not r.get("owner"):
            issues.append(f"missing_responsibility_owner:{r.get('responsibility_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def role_integrity() -> dict:
    """역할 무결성: 유닛 존재(orphan agent), 중복 역할(같은 unit+agent+role 중복)."""
    issues: list = []
    uids = {u.get("unit_id") for u in ledger.read_units()}
    seen: set = set()
    for r in ledger.read_roles():
        if r.get("unit_id") not in uids:
            issues.append(f"orphan_agent:{r.get('role_id')}")
        key = (r.get("unit_id"), r.get("agent"), r.get("role"))
        if key in seen:
            issues.append(f"duplicate_role:{r.get('role_id')}")
        seen.add(key)
    return {"ok": not issues, "issues": sorted(set(issues))}


def responsibility_integrity() -> dict:
    """책임 체인: input_sources 가 알려진 워크플로/유닛을 참조하는지(broken responsibility chain)."""
    issues: list = []
    known = ({w.get("workflow_id") for w in ledger.read_workflows()}
             | {u.get("unit_id") for u in ledger.read_units()})
    for r in ledger.read_responsibilities():
        for src in r.get("input_sources", []):
            if src.startswith("ROK:") or src.startswith("ROU:"):
                if src not in known:
                    issues.append(f"broken_chain:{r.get('responsibility_id')}:{src}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def dependency_integrity() -> dict:
    """의존 무결성: 워크플로 depends_on 이 존재 워크플로 참조 + 순환(circular dependency)."""
    issues: list = []
    wids = {w.get("workflow_id") for w in ledger.read_workflows()}
    edges: list = []
    for w in ledger.read_workflows():
        for d in w.get("depends_on", []):
            if d not in wids:
                issues.append(f"dangling_dependency:{w.get('workflow_id')}:{d}")
            edges.append((w.get("workflow_id"), d))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("circular_dependency:" + "->".join(cyc))
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


def snapshot_consistency() -> dict:
    """스냅샷 일관성: 저장된 unit_count/role_count == 분포 합계(corrupted snapshot)."""
    issues: list = []
    for s in ledger.read_snapshots():
        if sum((s.get("unit_type_distribution") or {}).values()) != s.get("unit_count"):
            issues.append(f"corrupted_unit_snapshot:{s.get('snapshot_id')}")
        if sum((s.get("role_distribution") or {}).values()) != s.get("role_count"):
            issues.append(f"corrupted_role_snapshot:{s.get('snapshot_id')}")
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
    role = role_integrity()
    responsibility = responsibility_integrity()
    dependency = dependency_integrity()
    lineage = lineage_integrity()
    snapshot = snapshot_consistency()
    ok = (ok and lifecycle["ok"] and ownership["ok"] and role["ok"] and responsibility["ok"]
          and dependency["ok"] and lineage["ok"] and snapshot["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "ownership": ownership, "role": role, "responsibility": responsibility,
            "dependency": dependency, "lineage": lineage, "snapshot": snapshot}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "org_event_count": r1.org_event_count, "unit_count": r1.unit_count,
            "role_count": r1.role_count}
