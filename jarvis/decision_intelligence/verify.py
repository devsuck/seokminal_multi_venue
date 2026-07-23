"""Research Decision Intelligence 검증 (P10.7) — 체인 무결성·변조·중복·리플레이·계보 검증. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계보: dangling reference·아티팩트
dangling parent·순환 탐지. replay: 동일 상태 리포트 재계산 → 동일 산출. **변경/선택/배포/실행 없음.**
"""
from __future__ import annotations

from jarvis.decision_intelligence import ledger
from jarvis.decision_intelligence.models import GENESIS, content_hash, detect_cycle


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
    """Source→Candidate→Evaluation→Scorecard→Tradeoff→Report 계보 검증.

    dangling scorecard(미존재 후보/프레임워크)·dangling tradeoff/report(미존재 세션)·
    아티팩트 dangling parent·circular dependency 탐지.
    """
    issues: list = []
    candidate_ids = {c.get("candidate_id") for c in ledger.distinct_candidates()}
    session_ids = {s.get("session_id") for s in ledger.distinct_sessions()}
    framework_ids = {f.get("framework_id") for f in ledger.read_frameworks()}

    for s in ledger.read_scorecards():
        if s.get("candidate_id") and s.get("candidate_id") not in candidate_ids:
            issues.append(f"dangling_scorecard_candidate:{s.get('scorecard_id')}")
        if s.get("framework_id") and s.get("framework_id") not in framework_ids:
            issues.append(f"dangling_scorecard_framework:{s.get('scorecard_id')}")
        if s.get("session_id") and s.get("session_id") not in session_ids:
            issues.append(f"dangling_scorecard_session:{s.get('scorecard_id')}")
    for t in ledger.read_tradeoffs():
        if t.get("session_id") and t.get("session_id") not in session_ids:
            issues.append(f"dangling_tradeoff:{t.get('tradeoff_id')}")
    for r in ledger.read_reports():
        if r.get("session_id") and r.get("session_id") not in session_ids:
            issues.append(f"dangling_report:{r.get('report_id')}")

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


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lineage = lineage_validation()
    ok = ok and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 결정 지원 리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.generate_report(now)
    r2 = engine.generate_report(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "candidate_count": r1.candidate_count,
            "session_count": r1.session_count,
            "scorecard_count": r1.scorecard_count}
