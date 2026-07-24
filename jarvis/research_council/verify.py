"""Research Council 검증 (P11.6) — 체인·변조·중복·생애주기·합의 결정성·소수보존·계보·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 세션 생애주기 전이 합법성. 합의 결정성:
저장된 outcome == 투표로 재계산. 소수 보존: 합의별 소수의견 기록 존재 여부(패배 입장 투표자). 계보: 아티팩트
parent dangling·순환. **변경/실행/승인/배포 없음.**
"""
from __future__ import annotations

from jarvis.research_council import ledger
from jarvis.research_council.models import (
    GENESIS,
    S_CREATED,
    STANCE_AGAINST,
    STANCE_FOR,
    can_transition,
    consensus_outcome,
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
    """세션별 생애주기 전이 합법성(순차)."""
    issues: list = []
    by_session: dict = {}
    for ev in ledger.read_session_events():
        by_session.setdefault(ev.get("session_id"), []).append(ev)
    for sid, evs in sorted(by_session.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != S_CREATED:
                    issues.append(f"bad_initial:{sid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"illegal:{sid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def consensus_determinism() -> dict:
    """합의 결정성: 저장된 outcome == 해당 세션·주제 투표로 재계산한 outcome."""
    issues: list = []
    for c in ledger.read_consensus():
        votes = ledger.topic_votes(c.get("session_id"), c.get("topic"))
        recomputed = consensus_outcome([v.get("choice") for v in votes])
        if recomputed != c.get("outcome"):
            issues.append(f"outcome_mismatch:{c.get('consensus_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def minority_preservation() -> dict:
    """소수 보존: 소수(패배 입장) 투표자가 있는 합의는 소수의견 기록을 가진다."""
    issues: list = []
    for c in ledger.read_consensus():
        win = c.get("winning_stance")
        if win not in (STANCE_FOR, STANCE_AGAINST):
            continue
        losing_choice = "AGAINST" if win == STANCE_FOR else "FOR"
        losers = [v for v in ledger.topic_votes(c.get("session_id"), c.get("topic"))
                  if v.get("choice") == losing_choice]
        recorded = {m.get("participant") for m in ledger.consensus_minority(c.get("consensus_id"))}
        for v in losers:
            if v.get("participant") not in recorded:
                issues.append(f"unpreserved_minority:{c.get('consensus_id')}:{v.get('participant')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): dangling·순환 탐지."""
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
    lineage = lineage_integrity()
    minority = minority_preservation()
    ok = ok and lifecycle["ok"] and determinism["ok"] and lineage["ok"]
    if check_minority:
        ok = ok and minority["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "determinism": determinism, "lineage": lineage, "minority": minority}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "council_count": r1.council_count, "consensus_count": r1.consensus_count,
            "minority_count": r1.minority_count}
