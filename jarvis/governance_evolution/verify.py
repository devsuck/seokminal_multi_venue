"""Governance Evolution 검증 (P10.22) — 체인·변조·중복·상태 전이·타임라인·계보·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 상태 타임라인: 시퀀스 연속성·from/to 연결·
성숙도 전이 유효성(레벨 건너뛰기). 아티팩트 계보: dangling parent·순환. **변경/실행/승인/배포 없음.**
"""
from __future__ import annotations

from jarvis.governance_evolution import ledger
from jarvis.governance_evolution.models import (
    GENESIS,
    can_transition_state,
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


def state_timeline_validation() -> dict:
    """상태 타임라인: 그룹별 시퀀스 연속성·from/to 연결·성숙도 전이 유효성(레벨 건너뛰기 탐지)."""
    issues: list = []
    by_group: dict = {}
    for r in ledger.read_state_events():
        by_group.setdefault(r.get("state_id"), []).append(r)
    for sid, evs in by_group.items():
        evs_sorted = sorted(evs, key=lambda e: e.get("sequence", 0))
        expected_from = ""
        for i, e in enumerate(evs_sorted):
            if e.get("sequence") != i + 1:
                issues.append(f"broken_timeline:{sid}:seq{e.get('sequence')}")
            if e.get("from_maturity", "") != expected_from:
                issues.append(f"broken_timeline:{sid}:from{e.get('from_maturity')}")
            if not can_transition_state(e.get("from_maturity", ""), e.get("to_maturity", "")):
                issues.append(f"invalid_transition:{sid}:{e.get('from_maturity') or 'GENESIS'}->"
                              f"{e.get('to_maturity')}")
            expected_from = e.get("to_maturity", "")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_event_validation() -> dict:
    """중복 진화 이벤트: 동일 event_id 가 두 번 이상 나타나면 위반(append-only 무결성)."""
    issues: list = []
    seen: set = set()
    for e in ledger.read_events():
        eid = e.get("event_id")
        if eid in seen:
            issues.append(f"duplicate_event:{eid}")
        seen.add(eid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_validation() -> dict:
    """아티팩트 계보(parent 체인): dangling parent(dangling state)·순환 탐지."""
    issues: list = []
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"dangling:{a.get('artifact_id')}->{parent}")
            edges.append((a.get("artifact_id"), parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("lineage_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    timeline = state_timeline_validation()
    duplicate = duplicate_event_validation()
    lineage = lineage_validation()
    ok = ok and timeline["ok"] and duplicate["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "timeline": timeline,
            "duplicate": duplicate, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "event_count": r1.event_count, "state_count": r1.state_count,
            "assessment_count": r1.assessment_count}
