"""Autonomous Research OS 검증 (P13) — 체인·변조·중복·생애주기·참조·집계·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. OS 생애주기 전이 합법성(INITIALIZED 시작). 중복
OS(genesis 유일). 참조 무결성(에피소드→OS). 뷰·스냅샷 is_binding=False. 아티팩트 계보. **변경 없음. 하위 원장 쓰지 않음.**
"""
from __future__ import annotations

from jarvis.autonomous_research_os import ledger
from jarvis.autonomous_research_os.models import (
    OS_INITIALIZED,
    GENESIS,
    can_transition,
    content_hash,
    detect_cycle_check,
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


def _by_os() -> dict:
    out: dict = {}
    for ev in ledger.read_os_events():
        out.setdefault(ev.get("os_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """OS 생애주기 전이 합법성(순차, INITIALIZED 시작)."""
    issues: list = []
    for oid, evs in sorted(_by_os().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != OS_INITIALIZED:
                    issues.append(f"bad_initial:{oid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{oid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 OS: 같은 os_id 의 INITIALIZED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_os_events():
        if ev.get("from_state") == GENESIS:
            oid = ev.get("os_id")
            if oid in genesis_seen:
                issues.append(f"duplicate_os:{oid}")
            genesis_seen.add(oid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 에피소드/스냅샷/리포트의 os_id 가 존재하는지."""
    issues: list = []
    oids = set(ledger.os_ids())
    for e in ledger.read_episodes():
        if e.get("os_id") not in oids:
            issues.append(f"orphan_episode:{e.get('episode_id')}")
    for s in ledger.read_snapshots():
        if s.get("os_id") not in oids:
            issues.append(f"orphan_snapshot:{s.get('snapshot_id')}")
    for r in ledger.read_reports():
        if r.get("os_id") not in oids:
            issues.append(f"orphan_report:{r.get('report_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def binding_integrity() -> dict:
    """관찰 전용 무결성: 모든 뷰·스냅샷·리포트 is_binding=False (배포·결정 아님)."""
    issues: list = []
    for v in ledger.read_views():
        if v.get("is_binding") is not False:
            issues.append(f"binding_view:{v.get('view_id')}")
    for s in ledger.read_snapshots():
        if s.get("is_binding") is not False:
            issues.append(f"binding_snapshot:{s.get('snapshot_id')}")
    for r in ledger.read_reports():
        if r.get("is_binding") is not False:
            issues.append(f"binding_report:{r.get('report_id')}")
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
    lifecycle = lifecycle_integrity()
    duplicate = duplicate_integrity()
    reference = reference_integrity()
    binding = binding_integrity()
    lineage = lineage_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and reference["ok"] and binding["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "reference": reference, "binding": binding, "lineage": lineage}


def replay(engine, os: str, now: str = "") -> dict:
    """동일 상태 스냅샷 두 번 → 동일 산출(결정성). commit 없음."""
    s1 = engine.create_snapshot(os, now, commit=False)
    s2 = engine.create_snapshot(os, now, commit=False)
    return {"deterministic": s1.to_dict() == s2.to_dict(),
            "total_records": s1.total_records, "episode_count": s1.episode_count}
