"""Self Audit Intelligence 자체 검증 (P10.24) — 감사 계층 자신의 원장 무결성. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 감사 실행: 이벤트 소싱 전이 유효성.
아티팩트 계보: dangling parent·순환. **변경/실행/복구/수정 없음.** (상위 계층 감사는 engine 이 담당.)
"""
from __future__ import annotations

from jarvis.self_audit_intelligence import ledger
from jarvis.self_audit_intelligence.models import (
    GENESIS,
    RUN_TRANSITIONS,
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


def run_transition_validation() -> dict:
    """감사 실행 이벤트 소싱 전이 유효성: 각 run_id 별 from_state→to_state 가 허용 표에 있는지."""
    issues: list = []
    by_group: dict = {}
    for r in ledger.read_run_events():
        by_group.setdefault(r.get("run_id"), []).append(r)
    for rid, evs in by_group.items():
        for e in evs:
            frm, to = e.get("from_state", ""), e.get("to_state", "")
            if to not in RUN_TRANSITIONS.get(frm, set()):
                issues.append(f"invalid_transition:{rid}:{frm or 'GENESIS'}->{to}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_validation() -> dict:
    """감사 아티팩트 계보(parent 체인): dangling parent·순환 탐지."""
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
    run_tr = run_transition_validation()
    lineage = lineage_validation()
    ok = ok and run_tr["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "run_transitions": run_tr,
            "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "audit_count": r1.audit_count, "run_count": r1.run_count,
            "check_count": r1.check_count}
