"""Portfolio Research 검증 (P10.4) — 체인 무결성·변조·중복·리플레이·계보 검증. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계보: 미존재 study 참조·깨진
아티팩트·순환 의존 탐지. replay: 동일 상태 리포트 재계산 → 동일 산출. **변경/배분/실행 없음.**
"""
from __future__ import annotations

from jarvis.portfolio_research import ledger
from jarvis.portfolio_research.models import GENESIS, content_hash, detect_cycle


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
    """Portfolio→Hypothesis→Construction→Backtest→RiskAnalysis 계보 검증.

    broken lineage(dangling parent) · circular dependency · dangling backtest/risk(미존재 study).
    """
    issues: list = []
    study_ids = {s.get("study_id") for s in ledger.read_studies()}
    for b in ledger.read_backtests():
        if b.get("study_id") and b.get("study_id") not in study_ids:
            issues.append(f"dangling_backtest:{b.get('backtest_id')}")
    for r in ledger.read_risk():
        if r.get("study_id") and r.get("study_id") not in study_ids:
            issues.append(f"dangling_risk:{r.get('analysis_id')}")

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
    """동일 상태 포트폴리오 연구 리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.generate_portfolio_report(now)
    r2 = engine.generate_portfolio_report(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "portfolio_count": r1.portfolio_count, "state_distribution": r1.state_distribution}
