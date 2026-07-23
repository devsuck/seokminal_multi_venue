"""Research Compliance 검증 (P10.19) — 체인·변조·중복·전이·증거 참조·계보·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 위반: 이벤트 소싱 전이 유효성. 점검:
규칙 참조 존재. 증거 참조: 점검의 evidence_reference·위반 evidence 가 증거 원장에 존재하는지(missing/dangling).
아티팩트 계보: dangling parent·순환. **변경/실행/수정/승인/배포 없음.**
"""
from __future__ import annotations

from jarvis.research_compliance import ledger
from jarvis.research_compliance.models import (
    GENESIS,
    VIOLATION_TRANSITIONS,
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


def violation_transition_validation() -> dict:
    """위반 이벤트 소싱 전이 유효성: 각 violation_id 별 from_state→to_state 가 허용 표에 있는지."""
    issues: list = []
    by_group: dict = {}
    for r in ledger.read_violation_events():
        by_group.setdefault(r.get("violation_id"), []).append(r)
    for vid, evs in by_group.items():
        for e in evs:
            frm, to = e.get("from_state", ""), e.get("to_state", "")
            if to not in VIOLATION_TRANSITIONS.get(frm, set()):
                issues.append(f"invalid_transition:{vid}:{frm or 'GENESIS'}->{to}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def rule_reference_validation() -> dict:
    """점검의 rule_id 가 규칙 원장에 존재하는지(missing rule)."""
    issues: list = []
    rule_ids = {r.get("rule_id") for r in ledger.read_rules()}
    for c in ledger.read_checks():
        if c.get("rule_id") not in rule_ids:
            issues.append(f"missing_rule:{c.get('check_id')}->{c.get('rule_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def evidence_reference_validation() -> dict:
    """증거 참조 무결성: 점검의 evidence_reference 가 지정되었으나 증거 원장에 없으면 dangling."""
    issues: list = []
    ev_ids = {e.get("evidence_id") for e in ledger.read_evidence()}
    for c in ledger.read_checks():
        ref = c.get("evidence_reference")
        if ref and ref.startswith("RCE:") and ref not in ev_ids:
            issues.append(f"dangling_evidence:{c.get('check_id')}->{ref}")
    return {"ok": not issues, "issues": sorted(set(issues)), "n_evidence": len(ev_ids)}


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
    violation_tr = violation_transition_validation()
    rule_ref = rule_reference_validation()
    evidence_ref = evidence_reference_validation()
    lineage = lineage_validation()
    ok = ok and violation_tr["ok"] and rule_ref["ok"] and evidence_ref["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "violation_transitions": violation_tr,
            "rule_reference": rule_ref, "evidence_reference": evidence_ref, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "rule_count": r1.rule_count, "check_count": r1.check_count,
            "violation_count": r1.violation_count}
