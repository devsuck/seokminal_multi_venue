"""Governance Orchestration 검증 (P10.23) — 체인·변조·중복·전이·의존·계보·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 레이어/스냅샷: 이벤트 소싱 전이 유효성.
의존 그래프: 자기참조·순환. 아티팩트 계보: dangling parent·순환. **변경/실행/배포/config·permission 변경 없음.**
"""
from __future__ import annotations

from jarvis.governance_orchestration import ledger
from jarvis.governance_orchestration.models import (
    GENESIS,
    LAYER_TRANSITIONS,
    SNAPSHOT_TRANSITIONS,
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


def _validate_transitions(events: list, id_field_group: str, table: dict) -> dict:
    issues: list = []
    by_group: dict = {}
    for r in events:
        by_group.setdefault(r.get(id_field_group), []).append(r)
    for gid, evs in by_group.items():
        for e in evs:
            frm, to = e.get("from_state", ""), e.get("to_state", "")
            if to not in table.get(frm, set()):
                issues.append(f"invalid_transition:{gid}:{frm or 'GENESIS'}->{to}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def layer_transition_validation() -> dict:
    return _validate_transitions(ledger.read_layer_events(), "layer_id", LAYER_TRANSITIONS)


def snapshot_transition_validation() -> dict:
    return _validate_transitions(ledger.read_snapshot_events(), "snapshot_id", SNAPSHOT_TRANSITIONS)


def dependency_validation() -> dict:
    """의존 그래프: 자기참조·순환 탐지."""
    issues: list = []
    deps = ledger.read_dependencies()
    for d in deps:
        if d.get("from_layer") == d.get("to_layer"):
            issues.append(f"self_dependency:{d.get('dependency_id')}")
    edges = [(d.get("from_layer"), d.get("to_layer")) for d in deps]
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("dependency_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_dependencies": len(deps)}


def lineage_validation() -> dict:
    """아티팩트 계보(parent 체인): dangling parent·순환 탐지."""
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
    layer_tr = layer_transition_validation()
    snapshot_tr = snapshot_transition_validation()
    dependency = dependency_validation()
    lineage = lineage_validation()
    ok = ok and layer_tr["ok"] and snapshot_tr["ok"] and dependency["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "layer_transitions": layer_tr,
            "snapshot_transitions": snapshot_tr, "dependency": dependency, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "layer_count": r1.layer_count, "snapshot_count": r1.snapshot_count,
            "conflict_count": r1.conflict_count}
