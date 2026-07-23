"""Research OS Orchestration 검증 (P11) — 체인·변조·중복·워크플로/계보/의존 그래프·계보 무결성. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계보/의존: 순환·미등록 노드.
아티팩트: missing parent·순환. **변경/실행/배포/config변경 없음.**
"""
from __future__ import annotations

from jarvis.research_os import ledger
from jarvis.research_os.models import EDGE_TYPES, GENESIS, NODE_TYPES, content_hash, detect_cycle


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
    """연구 계보 그래프: 미등록 노드 유형·순환 탐지."""
    issues: list = []
    lin = ledger.read_lineage()
    for e in lin:
        if e.get("from_type") not in NODE_TYPES or e.get("to_type") not in NODE_TYPES:
            issues.append(f"invalid_node:{e.get('lineage_id')}")
        if e.get("edge_type") not in EDGE_TYPES:
            issues.append(f"invalid_edge:{e.get('lineage_id')}")
    edges = [(e.get("from_node"), e.get("to_node")) for e in lin]
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("lineage_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_lineage": len(lin)}


def dependency_validation() -> dict:
    """레이어 의존 그래프: 순환 탐지."""
    deps = ledger.read_dependencies()
    edges = [(d.get("from_layer"), d.get("to_layer")) for d in deps]
    cyc = detect_cycle(edges)
    issues = ["dependency_cycle:" + "->".join(cyc)] if cyc else []
    return {"ok": not issues, "issues": issues, "n_dependencies": len(deps)}


def workflow_validation() -> dict:
    """워크플로 그래프: 각 워크플로 엣지 순환·미등록 노드 유형 탐지."""
    issues: list = []
    for w in ledger.distinct_workflows():
        for nd in w.get("nodes", []):
            if isinstance(nd, dict) and nd.get("type") not in NODE_TYPES:
                issues.append(f"invalid_node:{w.get('workflow_id')}")
        pairs = []
        for e in w.get("edges", []):
            if len(e) >= 3:
                pairs.append((e[0], e[2]))
            elif len(e) == 2:
                pairs.append((e[0], e[1]))
        cyc = detect_cycle(pairs)
        if cyc:
            issues.append(f"workflow_cycle:{w.get('workflow_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def artifact_validation() -> dict:
    """아티팩트 계보: missing parent·순환 탐지."""
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
    lineage = lineage_validation()
    dependency = dependency_validation()
    workflow = workflow_validation()
    artifact = artifact_validation()
    ok = ok and lineage["ok"] and dependency["ok"] and workflow["ok"] and artifact["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lineage": lineage,
            "dependency": dependency, "workflow": workflow, "artifact": artifact}


def replay(engine, now: str = "") -> dict:
    """동일 상태 오케스트레이션 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "layer_count": r1.layer_count, "workflow_count": r1.workflow_count,
            "event_count": r1.event_count}
