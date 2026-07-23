"""Research Meta Intelligence 검증 (P10.12) — 체인 무결성·변조·중복·계보·진화 그래프 순환. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계보: missing parent·broken lineage·
아티팩트 순환. 진화 그래프: 방향성 엣지 순환. **변경/실행/배포 없음.**
"""
from __future__ import annotations

from jarvis.meta_intelligence import ledger
from jarvis.meta_intelligence.models import ART_EDGE, GENESIS, content_hash, detect_cycle


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
    """Source→Outcome→Pattern→Failure→Quality→Insight→Report 계보 검증.

    dangling quality(미존재 결과 대상)·아티팩트 missing parent·순환 탐지.
    """
    issues: list = []
    outcome_ids = {o.get("outcome_id") for o in ledger.distinct_outcomes()}
    research_objects = {o.get("research_object") for o in ledger.distinct_outcomes()}

    for s in ledger.read_quality_scores():
        ro = s.get("research_object")
        if ro and research_objects and ro not in research_objects and ro not in outcome_ids:
            # 품질 대상이 어떤 결과 대상과도 매칭 안 됨 → 정보성 경고(계보 단절 가능)
            issues.append(f"unlinked_quality:{s.get('score_id')}")

    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    # 계보 엣지(parent 링크)만 순환/미존재 검사(진화 엣지는 별도).
    lineage_edges = []
    for a in arts:
        if a.get("artifact_type") == ART_EDGE:
            continue
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"broken_lineage:{a.get('artifact_id')}->{parent}")
            lineage_edges.append((a.get("artifact_id"), parent))
    cyc = detect_cycle(lineage_edges)
    if cyc:
        issues.append("artifact_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}


def evolution_graph_validation() -> dict:
    """진화 그래프(엣지 아티팩트) 방향성 순환 탐지."""
    edges = [(a.get("from_ref"), a.get("to_ref")) for a in ledger.read_artifacts()
             if a.get("artifact_type") == ART_EDGE]
    cyc = detect_cycle(edges)
    issues = ["evolution_cycle:" + "->".join(cyc)] if cyc else []
    return {"ok": not issues, "issues": issues, "n_edges": len(edges)}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lineage = lineage_validation()
    evolution = evolution_graph_validation()
    ok = ok and lineage["ok"] and evolution["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lineage": lineage,
            "evolution": evolution}


def replay(engine, now: str = "") -> dict:
    """동일 상태 메타 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "outcome_count": r1.outcome_count, "mean_quality": r1.mean_quality,
            "insight_count": r1.insight_count}
