"""Research Conflict Resolution 검증 (P11.9) — 체인·변조·중복·생애주기·합의 결정성·참조·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 충돌 생애주기 전이 합법성. 합의 결정성:
저장된 computed_type == 지지·증거로 재계산. 참조 무결성: 증거→주장, 포지션→주장 dangling. 아티팩트 계보:
dangling·순환. **변경/실행/승인/수정 없음.**
"""
from __future__ import annotations

from jarvis.research_conflict_resolution import ledger
from jarvis.research_conflict_resolution.models import (
    C_DETECTED,
    GENESIS,
    can_transition,
    content_hash,
    derive_resolution,
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
    """충돌별 생애주기 전이 합법성(순차)."""
    issues: list = []
    by_conflict: dict = {}
    for ev in ledger.read_case_events():
        by_conflict.setdefault(ev.get("conflict_id"), []).append(ev)
    for cid, evs in sorted(by_conflict.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != C_DETECTED:
                    issues.append(f"bad_initial:{cid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"illegal:{cid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def consensus_determinism() -> dict:
    """합의 결정성: 저장된 computed_type == 지지·증거로 재계산한 유형."""
    issues: list = []
    for k in ledger.read_consensus():
        rtype, _ = derive_resolution(dict(k.get("support_tally", {})),
                                     dict(k.get("evidence_tally", {})))
        if rtype != k.get("computed_type"):
            issues.append(f"consensus_mismatch:{k.get('consensus_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 증거→주장, 포지션→주장 dangling 탐지."""
    issues: list = []
    cids = {c.get("claim_id") for c in ledger.read_claims()}
    for ev in ledger.read_evidence():
        if ev.get("claim_id") not in cids:
            issues.append(f"dangling_evidence:{ev.get('evidence_id')}")
    for p in ledger.read_positions():
        if p.get("backed_claim") not in cids:
            issues.append(f"dangling_position:{p.get('position_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): dangling·순환."""
    issues: list = []
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"dangling:{a.get('artifact_id')}")
            edges.append((a.get("artifact_id"), parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def minority_preservation() -> dict:
    """소수 보존: 해소된 충돌에서 승리 주장 외 지지 에이전트는 소수의견 기록을 가진다."""
    issues: list = []
    for cid in ledger.conflict_ids():
        outcomes = ledger.conflict_outcomes(cid)
        if not outcomes:
            continue
        win = outcomes[-1].get("winning_claim")
        if not win:
            continue
        recorded = {m.get("agent") for m in ledger.conflict_minority(cid)}
        for p in ledger.conflict_positions(cid):
            if p.get("backed_claim") != win and p.get("agent") not in recorded:
                issues.append(f"unpreserved:{cid}:{p.get('agent')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain(check_minority: bool = False) -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lifecycle = lifecycle_integrity()
    determinism = consensus_determinism()
    reference = reference_integrity()
    lineage = lineage_integrity()
    minority = minority_preservation()
    ok = ok and lifecycle["ok"] and determinism["ok"] and reference["ok"] and lineage["ok"]
    if check_minority:
        ok = ok and minority["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "determinism": determinism, "reference": reference, "lineage": lineage,
            "minority": minority}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "claim_count": r1.claim_count, "consensus_count": r1.consensus_count,
            "minority_count": r1.minority_count}
