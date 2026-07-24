"""Adaptive Research Loop 검증 (P12.4) — 체인·변조·중복·생애주기·리뷰기록·참조·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 제안 생애주기 전이 합법성(OBSERVED 시작).
중복 제안(genesis 유일). 인간 리뷰 무결성(RECORDED 이전 REVIEWED 이벤트에 reviewer). 참조 무결성(피드백/제안/
적응/메트릭의 사이클 존재). **변경/실행/자동 수정 없음.**
"""
from __future__ import annotations

from jarvis.adaptive_research_loop import ledger
from jarvis.adaptive_research_loop.models import (
    GENESIS,
    L_OBSERVED,
    L_REVIEWED,
    can_transition,
    content_hash,
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


def _by_proposal() -> dict:
    out: dict = {}
    for ev in ledger.read_proposal_events():
        out.setdefault(ev.get("proposal_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """제안 생애주기 전이 합법성(순차, OBSERVED 시작)."""
    issues: list = []
    for pid, evs in sorted(_by_proposal().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != L_OBSERVED:
                    issues.append(f"bad_initial:{pid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{pid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 제안: 같은 proposal_id 의 OBSERVED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_proposal_events():
        if ev.get("from_state") == GENESIS:
            pid = ev.get("proposal_id")
            if pid in genesis_seen:
                issues.append(f"duplicate_proposal:{pid}")
            genesis_seen.add(pid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def review_integrity() -> dict:
    """인간 리뷰 무결성: RECORDED 상태 제안은 reviewer 를 가진 REVIEWED 이벤트가 선행한다."""
    issues: list = []
    for pid, evs in _by_proposal().items():
        states = [e.get("to_state") for e in evs]
        if "RECORDED" in states:
            reviewed = [e for e in evs if e.get("to_state") == L_REVIEWED and e.get("reviewer")]
            if not reviewed:
                issues.append(f"recorded_without_human_review:{pid}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 피드백/제안/적응/메트릭의 사이클이 존재하는지."""
    issues: list = []
    cids = {c.get("cycle_id") for c in ledger.read_cycles()}
    for f in ledger.read_feedback():
        if f.get("cycle_id") not in cids:
            issues.append(f"inconsistent_feedback_cycle:{f.get('feedback_id')}")
    for pid, evs in _by_proposal().items():
        if evs[0].get("cycle_id") not in cids:
            issues.append(f"inconsistent_proposal_cycle:{pid}")
    for a in ledger.read_adaptations():
        if a.get("cycle_id") not in cids:
            issues.append(f"inconsistent_adaptation_cycle:{a.get('adaptation_id')}")
    for m in ledger.read_metrics():
        if m.get("cycle_a") not in cids or m.get("cycle_b") not in cids:
            issues.append(f"inconsistent_metric_cycle:{m.get('metric_id')}")
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
    review = review_integrity()
    reference = reference_integrity()
    ok = ok and lifecycle["ok"] and duplicate["ok"] and review["ok"] and reference["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "review": review, "reference": reference}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "proposal_event_count": r1.proposal_event_count,
            "adaptation_count": r1.adaptation_count}
