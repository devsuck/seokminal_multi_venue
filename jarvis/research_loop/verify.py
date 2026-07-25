"""Research Loop 검증 (C5) — 체인·단계 생애주기·승인 게이트·재현. 읽기전용.

핵심 불변식: EXECUTION 단계에 진입한 모든 루프는 반드시 그 전에 사람 APPROVED 검토가 존재해야 한다.
"""
from __future__ import annotations

from jarvis.research_loop import ledger
from jarvis.research_loop import models as M
from jarvis.research_loop.models import GENESIS, content_hash


def _verify_records(records, id_field) -> dict:
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


def _group(records, key) -> dict:
    out: dict = {}
    for r in records:
        out.setdefault(r.get(key), []).append(r)
    return out


def stage_lifecycle_integrity() -> dict:
    issues = []
    for lid, evs in sorted(_group(ledger.read_loop_events(), "loop_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_stage")
            if prev is None:
                if to != M.S_OBSERVATION:
                    issues.append(f"bad_initial:{lid}:{to}")
            elif not M.can_stage_transition(prev, to):
                issues.append(f"invalid_transition:{lid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def approval_gate_integrity() -> dict:
    """EXECUTION 에 진입한 모든 루프는 사전에 사람 APPROVED 검토가 있어야 한다(게이트 우회 탐지)."""
    issues = []
    approved_loops = set()
    for r in ledger.read_reviews():
        if r.get("decision") == M.REVIEW_APPROVED:
            approved_loops.add(r.get("loop_id"))
        if r.get("is_human") is not True:
            issues.append(f"non_human_review:{r.get('review_id')}")
    for ev in ledger.read_loop_events():
        if ev.get("to_stage") in M.APPROVAL_GATED_STAGES and ev.get("loop_id") not in approved_loops:
            issues.append(f"ungated_execution:{ev.get('loop_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues = []
    seen = set()
    for ev in ledger.read_loop_events():
        if ev.get("from_stage") == GENESIS:
            lid = ev.get("loop_id")
            if lid in seen:
                issues.append(f"duplicate_loop:{lid}")
            seen.add(lid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    stage = stage_lifecycle_integrity()
    gate = approval_gate_integrity()
    dup = duplicate_integrity()
    ok = ok and stage["ok"] and gate["ok"] and dup["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "stage_lifecycle": stage,
            "approval_gate": gate, "duplicate": dup}


def replay(engine, now="") -> dict:
    s1 = engine.summary(now)
    s2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": s1.to_dict() == s2.to_dict() and p1.to_dict() == p2.to_dict(),
            "loop_count": s1.loop_count}
