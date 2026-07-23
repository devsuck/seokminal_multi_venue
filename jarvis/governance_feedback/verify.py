"""Governance Feedback 검증 (P10.20) — 체인·변조·중복·전이·집계·참조·계보·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 이슈: 이벤트 소싱 전이 유효성. 집계:
aggregation_id 결정성(period 재계산). 참조/계보: 아티팩트 dangling parent·순환. **변경/실행/승인/배포 없음.**
"""
from __future__ import annotations

from jarvis.governance_feedback import ledger
from jarvis.governance_feedback.models import (
    GENESIS,
    ISSUE_TRANSITIONS,
    aggregation_id as _aggregation_id,
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


def issue_transition_validation() -> dict:
    """이슈 이벤트 소싱 전이 유효성: 각 issue_id 별 from_state→to_state 가 허용 표에 있는지."""
    issues: list = []
    by_group: dict = {}
    for r in ledger.read_issue_events():
        by_group.setdefault(r.get("issue_id"), []).append(r)
    for iid, evs in by_group.items():
        for e in evs:
            frm, to = e.get("from_state", ""), e.get("to_state", "")
            if to not in ISSUE_TRANSITIONS.get(frm, set()):
                issues.append(f"invalid_transition:{iid}:{frm or 'GENESIS'}->{to}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def aggregation_validation() -> dict:
    """집계 무결성: aggregation_id 가 period 로부터 결정적으로 재계산되는지(invalid aggregation)."""
    issues: list = []
    for a in ledger.read_aggregations():
        if a.get("aggregation_id") != _aggregation_id(a.get("period", "")):
            issues.append(f"invalid_aggregation:{a.get('aggregation_id')}")
    return {"ok": not issues, "issues": sorted(set(issues)),
            "n_aggregations": len(ledger.read_aggregations())}


def reference_validation() -> dict:
    """참조 무결성: 아티팩트 parent 가 계보에 존재하는지(dangling reference)."""
    issues: list = []
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    for a in arts:
        parent = a.get("parent_artifact")
        if parent and parent not in ids:
            issues.append(f"dangling_reference:{a.get('artifact_id')}->{parent}")
    return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}


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
    issue_tr = issue_transition_validation()
    aggregation = aggregation_validation()
    reference = reference_validation()
    lineage = lineage_validation()
    ok = ok and issue_tr["ok"] and aggregation["ok"] and reference["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "issue_transitions": issue_tr,
            "aggregation": aggregation, "reference": reference, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "feedback_count": r1.feedback_count, "issue_count": r1.issue_count,
            "pattern_count": r1.pattern_count}
