"""Alpha Intelligence 검증 (P10.3) — 체인 무결성·변조·중복·리플레이·계보 검증. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계보: 미존재 피처·깨진 참조·
순환 의존 탐지. replay: 동일 상태 리포트 재계산 → 동일 산출. **변경/실행/거래 없음.**
"""
from __future__ import annotations

from jarvis.alpha_intelligence import ledger
from jarvis.alpha_intelligence.models import GENESIS, content_hash, detect_cycle


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
    """Signal→Feature→Dataset→Experiment→Evaluation 계보 검증.

    missing feature · invalid dataset version · broken lineage(dangling parent) · circular dependency.
    """
    issues: list = []
    feat_ids = ledger.feature_ids()
    exp_ids = {e.get("experiment_id") for e in ledger.read_experiments()}

    # missing feature / invalid dataset (실험이 참조하는 피처 미등록·데이터셋 버전 결측)
    for e in ledger.read_experiments():
        for fdep in e.get("feature_dependencies", []) or []:
            if fdep not in feat_ids:
                issues.append(f"missing_feature:{e.get('experiment_id')}:{fdep}")
        if not e.get("dataset_version"):
            issues.append(f"invalid_dataset:{e.get('experiment_id')}")

    # evaluation 이 미존재 실험 참조
    for v in ledger.read_evaluations():
        if v.get("experiment_id") not in exp_ids:
            issues.append(f"dangling_evaluation:{v.get('evaluation_id')}")

    # artifact broken lineage(dangling parent) + circular dependency
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
    """동일 상태 alpha 리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.generate_alpha_report(now)
    r2 = engine.generate_alpha_report(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "signal_count": r1.signal_count, "state_distribution": r1.state_distribution}
