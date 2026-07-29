"""Agent Research Governance 검증 (P10.6) — 체인 무결성·변조·중복·리플레이·계보 검증. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계보: 아티팩트 dangling parent·
순환 탐지. replay: 동일 상태 리포트 재계산 → 동일 산출. **변경/배분/실행/배포/승인 없음.**
"""
from __future__ import annotations

from jarvis.agent_governance import ledger
from jarvis.agent_governance.models import GENESIS, content_hash, detect_cycle


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


def lineage_validation() -> dict:
    """Agent→Request→Proposal→Experiment→Validation→Artifact 계보 검증.

    dangling parent(미존재 부모)·circular dependency·미존재 request/agent 참조.
    """
    issues: list = []
    agent_ids = {a.get("agent_id") for a in ledger.distinct_agents()}
    request_ids = {r.get("request_id") for r in ledger.distinct_requests()}

    for p in ledger.distinct_proposals():
        if p.get("request_id") and p.get("request_id") not in request_ids:
            issues.append(f"dangling_proposal:{p.get('proposal_id')}")
    for r in ledger.distinct_requests():
        if r.get("agent_id") and r.get("agent_id") not in agent_ids:
            issues.append(f"dangling_request:{r.get('request_id')}")

    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    edges = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"broken_lineage:{a.get('artifact_id')}->{parent}")
            edges.append((a.get("artifact_id"), parent))
    cycle = detect_cycle(edges)
    if cycle:
        issues.append("circular_dependency:" + "->".join(cycle))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}


def safety_audit() -> dict:
    """안전 불변식: 금지 행동은 전부 BLOCKED·수락 제안은 사람 검토를 거쳤는지."""
    issues: list = []
    for a in ledger.read_actions():
        if a.get("is_forbidden") and a.get("result") != "BLOCKED_FORBIDDEN":
            issues.append(f"forbidden_action_not_blocked:{a.get('action_id')}")
    # ACCEPTED 제안은 대응하는 사람 검토(APPROVE)가 있어야 한다.
    reviews = ledger.read_reviews()
    approved = {r.get("proposal_id") for r in reviews if r.get("decision") == "APPROVE"}
    for p in ledger.distinct_proposals():
        pid = p.get("proposal_id")
        evs = ledger.proposal_events_for(pid)
        state = evs[-1].get("to_state") if evs else ""
        if state == "ACCEPTED" and pid not in approved:
            issues.append(f"accepted_without_human_review:{pid}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lineage = lineage_validation()
    safety = safety_audit()
    ok = ok and lineage["ok"] and safety["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lineage": lineage, "safety": safety}


def replay(engine, now: str = "") -> dict:
    """동일 상태 거버넌스 리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.generate_report(now)
    r2 = engine.generate_report(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "agent_count": r1.agent_count,
            "agent_state_distribution": r1.agent_state_distribution,
            "blocked_action_count": r1.blocked_action_count}
