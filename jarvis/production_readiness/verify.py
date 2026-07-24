"""Production Readiness 검증 (P21) — 체인·중복·생애주기·참조·계보·비인가/자동 승인·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 후보/리뷰 상태 머신 전이 합법성(genesis 시작).
참조 무결성(체크/요구/리뷰/리스크→후보). 계보(dangling·순환). **비인가 승인·자동 승인 시도 탐지.** 변경 없음.
"""
from __future__ import annotations

from jarvis.production_readiness import ledger
from jarvis.production_readiness import models as M
from jarvis.production_readiness.models import GENESIS, content_hash, detect_cycle_check


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


def candidate_lifecycle_integrity() -> dict:
    """후보 상태 머신 전이 합법성(REGISTERED 시작)."""
    issues: list = []
    for cid, evs in sorted(_group(ledger.read_transitions(), "candidate_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.S_REGISTERED:
                    issues.append(f"bad_initial:{cid}:{to}")
            elif not M.can_candidate_transition(prev, to):
                issues.append(f"invalid_transition:{cid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def review_lifecycle_integrity() -> dict:
    """리뷰 상태 머신 전이 합법성(PENDING 시작)."""
    issues: list = []
    for rid, evs in sorted(_group(ledger.read_review_events(), "review_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.R_PENDING:
                    issues.append(f"bad_initial:{rid}:{to}")
            elif not M.can_review_transition(prev, to):
                issues.append(f"invalid_transition:{rid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 후보/리뷰: 후보는 유일 레코드, 리뷰 genesis(PENDING) 유일."""
    issues: list = []
    seen: set = set()
    for r in ledger.read_candidates():
        cid = r.get("candidate_id")
        if cid in seen:
            issues.append(f"duplicate_candidate:{cid}")
        seen.add(cid)
    rseen: set = set()
    for ev in ledger.read_review_events():
        if ev.get("from_state") == GENESIS:
            rid = ev.get("review_id")
            if rid in rseen:
                issues.append(f"duplicate_review:{rid}")
            rseen.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 전이/체크/요구/리뷰/리스크의 candidate_id 가 존재하는지(broken lineage·missing parent)."""
    issues: list = []
    cids = set(ledger.candidate_ids())
    for r in ledger.read_transitions():
        if r.get("candidate_id") not in cids:
            issues.append(f"orphan_transition:{r.get('transition_id')}")
    for r in ledger.read_checks():
        if r.get("candidate_id") not in cids:
            issues.append(f"orphan_check:{r.get('check_id')}")
    for r in ledger.read_requirements():
        if r.get("candidate_id") not in cids:
            issues.append(f"orphan_requirement:{r.get('requirement_id')}")
    for r in ledger.read_review_events():
        if r.get("candidate_id") not in cids:
            issues.append(f"orphan_review:{r.get('review_event_id')}")
    for r in ledger.read_risks():
        if r.get("candidate_id") not in cids:
            issues.append(f"orphan_risk:{r.get('risk_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def approval_integrity() -> dict:
    """비인가/자동 승인 탐지: 모든 리뷰 결정은 is_automatic=False + APPROVED 는 reviewer_id 필수.

    또한 READY_FOR_DEPLOYMENT 후보는 승인된(검토자 보유) 리뷰가 존재해야 한다.
    """
    issues: list = []
    for ev in ledger.read_review_events():
        if ev.get("is_automatic") is not False:
            issues.append(f"automatic_approval:{ev.get('review_event_id')}")
        if ev.get("to_state") == M.R_APPROVED and not ev.get("reviewer_id"):
            issues.append(f"unauthorized_approval:{ev.get('review_event_id')}")
    # READY_FOR_DEPLOYMENT 후보는 승인 리뷰 필요
    approved_by_cand: dict = {}
    grouped: dict = {}
    for ev in ledger.read_review_events():
        grouped.setdefault(ev.get("review_id"), []).append(ev)
    for rid, evs in grouped.items():
        last = evs[-1]
        if last.get("to_state") == M.R_APPROVED and last.get("reviewer_id"):
            approved_by_cand.setdefault(last.get("candidate_id"), True)
    for cid, evs in _group(ledger.read_transitions(), "candidate_id").items():
        states = [e.get("to_state") for e in evs]
        if M.S_READY_FOR_DEPLOYMENT in states and not approved_by_cand.get(cid):
            issues.append(f"deployment_ready_without_approval:{cid}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def evidence_integrity() -> dict:
    """체크는 증거 필수(evidence_required=True + 비어있지 않은 evidence)."""
    issues: list = []
    for c in ledger.read_checks():
        if c.get("evidence_required") is not True or not c.get("evidence"):
            issues.append(f"missing_evidence:{c.get('check_id')}")
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
    cand_life = candidate_lifecycle_integrity()
    review_life = review_lifecycle_integrity()
    duplicate = duplicate_integrity()
    reference = reference_integrity()
    approval = approval_integrity()
    evidence = evidence_integrity()
    lineage = lineage_integrity()
    ok = (ok and cand_life["ok"] and review_life["ok"] and duplicate["ok"] and reference["ok"]
          and approval["ok"] and evidence["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "candidate_lifecycle": cand_life,
            "review_lifecycle": review_life, "duplicate": duplicate, "reference": reference,
            "approval": approval, "evidence": evidence, "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "candidate_count": r1.candidate_count, "review_event_count": r1.review_event_count}
