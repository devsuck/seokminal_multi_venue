"""Research Planning Intelligence 검증 (P10.15) — 체인·변조·중복·계보·의존 그래프 순환. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 의존: 미등록 노드 유형·순환·
missing dependency. 계보: 아티팩트 missing parent·순환. **변경/실행/배포/배분 없음.**
"""
from __future__ import annotations

from jarvis.research_planning import ledger
from jarvis.research_planning.models import (
    EDGE_TYPES,
    GENESIS,
    NODE_TYPES,
    content_hash,
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


def dependency_validation() -> dict:
    """의존 그래프: 미등록 노드/엣지 유형·순환·미충족 의존(missing) 탐지."""
    issues: list = []
    deps = ledger.read_dependencies()
    node_ids: set = set()
    for d in deps:
        if d.get("from_type") not in NODE_TYPES or d.get("to_type") not in NODE_TYPES:
            issues.append(f"invalid_node:{d.get('dependency_id')}")
        if d.get("edge_type") not in EDGE_TYPES:
            issues.append(f"invalid_edge:{d.get('dependency_id')}")
        node_ids.add(d.get("from_node"))
        node_ids.add(d.get("to_node"))
    edges = [(d.get("from_node"), d.get("to_node")) for d in deps]
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("dependency_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_dependencies": len(deps)}


def blueprint_validation() -> dict:
    """청사진 필수 필드(objective/method) 존재 검증(형식)."""
    issues: list = []
    for b in ledger.read_blueprints():
        if not b.get("objective"):
            issues.append(f"blueprint_missing_objective:{b.get('blueprint_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_validation() -> dict:
    """Source→Opportunity→Hypothesis/Blueprint→Plan→Dependency→Priority→Report 계보 검증.

    아티팩트 missing parent·broken lineage·순환 탐지.
    """
    issues: list = []
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    edges = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"broken_lineage:{a.get('artifact_id')}->{parent}")
            edges.append((a.get("artifact_id"), parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("artifact_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    dependency = dependency_validation()
    blueprint = blueprint_validation()
    lineage = lineage_validation()
    ok = ok and dependency["ok"] and blueprint["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "dependency": dependency,
            "blueprint": blueprint, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 계획 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "opportunity_count": r1.opportunity_count, "plan_count": r1.plan_count,
            "dependency_count": r1.dependency_count}
