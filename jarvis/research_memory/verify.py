"""Research Memory Intelligence 검증 (P10.14) — 체인·변조·중복·계보·기억 그래프 순환. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 연결: 미등록 기억 참조·방향성 순환.
계보: 아티팩트 missing parent·순환. **변경/실행/배포/학습갱신 없음.**
"""
from __future__ import annotations

from jarvis.research_memory import ledger
from jarvis.research_memory.models import DIRECTED_RELATIONS, GENESIS, content_hash, detect_cycle


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
    """연결 그래프: 미등록 기억 참조·방향성 관계 순환 탐지."""
    issues: list = []
    memory_ids = {m.get("memory_id") for m in ledger.distinct_memories()}
    conns = ledger.read_connections()
    if memory_ids:
        for c in conns:
            for ref in (c.get("from_memory"), c.get("to_memory")):
                if ref not in memory_ids:
                    issues.append(f"unknown_memory:{c.get('connection_id')}:{ref}")
    directed = [(c.get("from_memory"), c.get("to_memory")) for c in conns
                if c.get("relation") in DIRECTED_RELATIONS]
    cyc = detect_cycle(directed)
    if cyc:
        issues.append("connection_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_connections": len(conns)}


def lineage_validation() -> dict:
    """Source→Memory→Lesson/Pattern→Connection→Retrieval→Cluster→Report 계보 검증.

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


def retrieval_determinism() -> dict:
    """검색 레코드의 retrieval_id 가 (query, matched) 로부터 재계산 일치하는지(변조 탐지)."""
    from jarvis.research_memory.models import retrieval_id as _rid
    issues: list = []
    for r in ledger.read_retrievals():
        expect = _rid(r.get("query", ""), r.get("matched_memories", []))
        if expect != r.get("retrieval_id"):
            issues.append(f"nondeterministic_retrieval:{r.get('retrieval_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    graph = graph_validation()
    lineage = lineage_validation()
    retrieval = retrieval_determinism()
    ok = ok and graph["ok"] and lineage["ok"] and retrieval["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "graph": graph, "lineage": lineage,
            "retrieval": retrieval}


def replay(engine, now: str = "") -> dict:
    """동일 상태 기억 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "memory_count": r1.memory_count, "connection_count": r1.connection_count,
            "retrieval_count": r1.retrieval_count}
