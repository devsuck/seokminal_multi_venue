"""Research Causal Intelligence 검증 (P10.11) — 체인 무결성·변조·중복·계보·순환·고아. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계보: missing parent·broken lineage·
아티팩트 순환. 그래프: 방향성 인과 엣지 순환·미등록 노드 참조. **변경/실행/배포 없음.**
"""
from __future__ import annotations

from jarvis.causal_intelligence import ledger
from jarvis.causal_intelligence.models import DIRECTED_EDGES, GENESIS, content_hash, detect_cycle


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


def graph_validation() -> dict:
    """그래프 무결성: 미등록 노드 참조·방향성 인과 엣지 순환 탐지."""
    issues: list = []
    variable_ids = {v.get("variable_id") for v in ledger.read_variables()}
    rels = ledger.read_relationships()
    if variable_ids:
        for r in rels:
            for ref in (r.get("cause"), r.get("effect")):
                if ref not in variable_ids:
                    issues.append(f"unknown_node:{r.get('study_id')}:{ref}")
    directed = [(r.get("cause"), r.get("effect")) for r in rels
                if r.get("edge_type") in DIRECTED_EDGES]
    cyc = detect_cycle(directed)
    if cyc:
        issues.append("causal_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_relationships": len(rels)}


def lineage_validation() -> dict:
    """Source→Variable→Hypothesis→Experiment→Evidence→Graph→Report 계보 검증.

    dangling hypothesis(미등록 변수)·dangling experiment(미존재 가설)·dangling evidence(미존재
    실험)·아티팩트 missing parent·순환 탐지.
    """
    issues: list = []
    variable_ids = {v.get("variable_id") for v in ledger.read_variables()}
    hypothesis_ids = {h.get("hypothesis_id") for h in ledger.distinct_hypotheses()}
    experiment_ids = {x.get("experiment_id") for x in ledger.distinct_experiments()}

    if variable_ids:
        for h in ledger.distinct_hypotheses():
            for ref in (h.get("cause_variable"), h.get("effect_variable")):
                if ref not in variable_ids:
                    issues.append(f"dangling_hypothesis:{h.get('hypothesis_id')}")
    for x in ledger.distinct_experiments():
        if x.get("hypothesis_id") and x.get("hypothesis_id") not in hypothesis_ids:
            issues.append(f"dangling_experiment:{x.get('experiment_id')}")
    for e in ledger.read_evidences():
        if e.get("experiment_id") and e.get("experiment_id") not in experiment_ids:
            issues.append(f"dangling_evidence:{e.get('evidence_id')}")

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
    graph = graph_validation()
    lineage = lineage_validation()
    ok = ok and graph["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "graph": graph, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 인과 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "variable_count": r1.variable_count, "hypothesis_count": r1.hypothesis_count,
            "relationship_count": r1.relationship_count}
