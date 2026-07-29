"""Research Evolution Governance 검증 (P10.16) — 체인·변조·중복·전이·계보 무결성·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 진화 사이클/개선 제안: 이벤트 소싱
전이 유효성. 계보: dangling parent·순환. **변경/실행/배포/수정/config변경 없음.**
"""
from __future__ import annotations

from jarvis.research_evolution import ledger
from jarvis.research_evolution.models import (
    CYCLE_TRANSITIONS,
    GENESIS,
    PROPOSAL_TRANSITIONS,
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
    """이벤트 소싱 원장의 전이 유효성: 각 그룹별 from_state→to_state 가 허용 표에 있는지."""
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


def cycle_transition_validation() -> dict:
    return _validate_transitions(ledger.read_cycle_events(), "cycle_id", CYCLE_TRANSITIONS)


def proposal_transition_validation() -> dict:
    return _validate_transitions(ledger.read_proposal_events(), "proposal_id",
                                 PROPOSAL_TRANSITIONS)


def lineage_validation() -> dict:
    """연구 진화 계보(아티팩트 parent 체인): dangling parent·순환 탐지."""
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
    cyc_tr = cycle_transition_validation()
    prop_tr = proposal_transition_validation()
    lineage = lineage_validation()
    ok = ok and cyc_tr["ok"] and prop_tr["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "cycle_transitions": cyc_tr,
            "proposal_transitions": prop_tr, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "object_count": r1.object_count, "failure_count": r1.failure_count,
            "learning_count": r1.learning_count}
