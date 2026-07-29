"""Research Simulation Environment 검증 (P10.8) — 체인 무결성·변조·중복·리플레이·계보 검증. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계보: dangling reference·아티팩트
dangling parent·순환 탐지. replay: 동일 상태 리포트/동일 런 결과 재계산 → 동일 산출. **변경/실행/배포 없음.**
"""
from __future__ import annotations

from jarvis.simulation_environment import ledger
from jarvis.simulation_environment.models import (
    GENESIS,
    content_hash,
    derive_metrics,
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


def lineage_validation() -> dict:
    """Candidate→Scenario→Run→Result→Comparison→Report 계보 검증.

    dangling run(미존재 시나리오)·dangling result(미존재 런)·dangling comparison(미존재 런)·
    아티팩트 dangling parent·circular dependency 탐지.
    """
    issues: list = []
    scenario_ids = {s.get("scenario_id") for s in ledger.distinct_scenarios()}
    run_ids = {r.get("run_id") for r in ledger.distinct_runs()}

    for r in ledger.distinct_runs():
        if r.get("scenario_reference") and r.get("scenario_reference") not in scenario_ids:
            issues.append(f"dangling_run_scenario:{r.get('run_id')}")
    for res in ledger.read_results():
        if res.get("run_id") and res.get("run_id") not in run_ids:
            issues.append(f"dangling_result_run:{res.get('result_id')}")
    for c in ledger.read_comparisons():
        for ref in (c.get("run_a"), c.get("run_b")):
            if ref and ref not in run_ids:
                issues.append(f"dangling_comparison_run:{c.get('comparison_id')}:{ref}")

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


def result_determinism() -> dict:
    """저장된 결과가 결정적 입력에서 재파생 가능한지 검증(변조/비결정성 탐지)."""
    issues: list = []
    checked = 0
    for res in ledger.read_results():
        det = res.get("deterministic_input", "")
        if det.startswith("explicit:"):
            continue  # 외부 제공 값은 재파생 대상 아님
        checked += 1
        if derive_metrics(det) != res.get("metrics"):
            issues.append(f"nondeterministic_result:{res.get('result_id')}")
    return {"ok": not issues, "issues": sorted(set(issues)), "checked": checked}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lineage = lineage_validation()
    determinism = result_determinism()
    ok = ok and lineage["ok"] and determinism["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lineage": lineage,
            "determinism": determinism}


def replay(engine, now: str = "") -> dict:
    """동일 상태 시뮬레이션 리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.generate_report(now)
    r2 = engine.generate_report(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "scenario_count": r1.scenario_count, "run_count": r1.run_count,
            "result_count": r1.result_count}
