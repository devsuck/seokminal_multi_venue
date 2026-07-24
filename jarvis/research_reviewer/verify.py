"""Research Reviewer 검증 (P11.5) — 체인·변조·중복·증거 연결·평결 결정성·자동결정 없음·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 증거 연결: 비평→리뷰, 증거→비평 dangling.
평결 결정성: 저장된 verdict == 차원 점수로 재계산한 verdict. 자동 결정 없음: is_decision=False·no_auto_decision.
**변경/실행/승인/삭제 없음.**
"""
from __future__ import annotations

from jarvis.research_reviewer import ledger
from jarvis.research_reviewer.models import (
    GENESIS,
    content_hash,
    overall_verdict,
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


def evidence_linkage() -> dict:
    """증거 연결 무결성: 비평→리뷰, 증거→비평 dangling 탐지."""
    issues: list = []
    rids = {r.get("review_id") for r in ledger.read_reviews()}
    cids = {c.get("critique_id") for c in ledger.read_critiques()}
    for c in ledger.read_critiques():
        if c.get("review_id") not in rids:
            issues.append(f"dangling_critique:{c.get('critique_id')}")
    for ev in ledger.read_evidence():
        if ev.get("critique_id") not in cids:
            issues.append(f"dangling_evidence:{ev.get('evidence_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verdict_determinism() -> dict:
    """평결 결정성: 저장된 verdict == 차원 점수로 재계산한 verdict."""
    issues: list = []
    for r in ledger.read_reviews():
        recomputed = overall_verdict(r.get("dimension_scores", {}))
        if recomputed != r.get("verdict"):
            issues.append(f"verdict_mismatch:{r.get('review_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def no_auto_decision() -> dict:
    """자동 결정 없음: 리뷰 no_auto_decision=True, 리포트 is_decision=False."""
    issues: list = []
    for r in ledger.read_reviews():
        if not r.get("no_auto_decision", False):
            issues.append(f"review_auto_decision:{r.get('review_id')}")
    for r in ledger.read_reports():
        if r.get("is_decision", False):
            issues.append(f"report_is_decision:{r.get('report_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    linkage = evidence_linkage()
    determinism = verdict_determinism()
    auto = no_auto_decision()
    ok = ok and linkage["ok"] and determinism["ok"] and auto["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "linkage": linkage,
            "determinism": determinism, "no_auto_decision": auto}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "review_count": r1.review_count, "critique_count": r1.critique_count,
            "report_count": r1.report_count}
