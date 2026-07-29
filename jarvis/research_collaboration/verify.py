"""Research Collaboration 검증 (P19) — 체인·변조·중복·생애주기(6종)·참조·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 협업/참여/제안/합의/갈등/사람검토 생애주기 전이
합법성(genesis 시작). 참조 무결성(참여/메시지/제안·합의/사람검토→협업). 계보(dangling·순환). **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_collaboration import ledger
from jarvis.research_collaboration import models as M
from jarvis.research_collaboration.models import GENESIS, content_hash, detect_cycle_check


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


def _group(records, key) -> dict:
    out: dict = {}
    for r in records:
        out.setdefault(r.get(key), []).append(r)
    return out


def _lifecycle(records, group_key, state_key, initial, can_fn) -> dict:
    """일반 이벤트-소싱 생애주기 검증: genesis initial 시작 + 합법 전이."""
    issues: list = []
    for gid, evs in sorted(_group(records, group_key).items()):
        prev = None
        for ev in evs:
            to = ev.get(state_key)
            if prev is None:
                if to != initial:
                    issues.append(f"bad_initial:{gid}:{to}")
            elif not can_fn(prev, to):
                issues.append(f"invalid_transition:{gid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def lifecycle_integrity() -> dict:
    checks = {
        "collaboration": _lifecycle(ledger.read_collab_events(), "collaboration_id", "to_state",
                                    M.C_CREATED, M.can_collab_transition),
        "participation": _lifecycle(ledger.read_participations(), "participant_id", "to_state",
                                    M.P_INVITED, M.can_participation_transition),
        "proposal": _lifecycle(ledger.read_proposal_events(), "proposal_id", "to_state",
                               M.PR_DRAFT, M.can_proposal_transition),
        "consensus": _lifecycle(ledger.read_consensus_events(), "consensus_id", "to_state",
                                M.CS_OPEN, M.can_consensus_transition),
        "conflict": _lifecycle(ledger.read_conflict_events(), "conflict_id", "to_state",
                               M.CF_OPEN, M.can_conflict_transition),
        "human_review": _lifecycle(ledger.read_human_review_events(), "human_review_id", "to_state",
                                   M.HR_REQUESTED, M.can_human_review_transition),
    }
    ok = all(v["ok"] for v in checks.values())
    return {"ok": ok, "checks": checks}


def duplicate_integrity() -> dict:
    """중복 엔티티: genesis 이벤트 유일(협업/참여/제안/합의/갈등/사람검토)."""
    issues: list = []
    specs = [
        (ledger.read_collab_events(), "collaboration_id", "from_state"),
        (ledger.read_participations(), "participant_id", "from_state"),
        (ledger.read_proposal_events(), "proposal_id", "from_state"),
        (ledger.read_consensus_events(), "consensus_id", "from_state"),
        (ledger.read_conflict_events(), "conflict_id", "from_state"),
        (ledger.read_human_review_events(), "human_review_id", "from_state"),
    ]
    for records, id_key, from_key in specs:
        seen: set = set()
        for ev in records:
            if ev.get(from_key) == GENESIS:
                gid = ev.get(id_key)
                if gid in seen:
                    issues.append(f"duplicate:{id_key}:{gid}")
                seen.add(gid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 참여/메시지/제안/합의/갈등/사람검토/리뷰의 collaboration_id 가 존재하는지."""
    issues: list = []
    cids = set(ledger.collaboration_ids())

    def _check(records, id_field, label):
        for r in records:
            if r.get("collaboration_id") not in cids:
                issues.append(f"orphan_{label}:{r.get(id_field)}")

    _check([e for e in ledger.read_participations() if e.get("from_state") == GENESIS],
           "participant_id", "participation")
    _check(ledger.read_messages(), "message_id", "message")
    _check([e for e in ledger.read_proposal_events() if e.get("from_state") == GENESIS],
           "proposal_id", "proposal")
    _check(ledger.read_reviews(), "review_id", "review")
    _check([e for e in ledger.read_consensus_events() if e.get("from_state") == GENESIS],
           "consensus_id", "consensus")
    _check([e for e in ledger.read_human_review_events() if e.get("from_state") == GENESIS],
           "human_review_id", "human_review")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): dangling·순환."""
    issues: list = []
    arts = ledger.read_artifacts()
    aids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in aids:
                issues.append(f"dangling_artifact:{a.get('artifact_id')}")
            edges.append((a.get("artifact_id"), parent))
    if detect_cycle_check(edges):
        issues.append("cycle_artifact")
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
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = ok and lifecycle["ok"] and duplicate["ok"] and reference["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "reference": reference, "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "collab_event_count": r1.collab_event_count, "message_count": r1.message_count}
