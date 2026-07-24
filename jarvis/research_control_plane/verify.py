"""Research Control Plane 검증 (P10.28) — 체인·변조·중복·의존성 그래프 무결성·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 시스템 맵: self·dangling target·missing
source·순환 의존성. **변경/실행/배포/할당/권한·설정 변경 없음.**
"""
from __future__ import annotations

from jarvis.research_control_plane import ledger
from jarvis.research_control_plane.models import (
    GENESIS,
    content_hash,
    dependency_issues,
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


def dependency_graph_integrity() -> dict:
    """시스템 맵 무결성: self·dangling target·missing source·순환 의존성 탐지."""
    nodes = sorted({c.get("name") for c in ledger.read_components() if c.get("name")})
    edges = sorted({(d.get("source"), d.get("target")) for d in ledger.read_dependencies()})
    issues = dependency_issues([(e[0], e[1]) for e in edges], nodes)
    return {"ok": not issues, "issues": issues, "node_count": len(nodes),
            "edge_count": len(edges)}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    graph = dependency_graph_integrity()
    ok = ok and graph["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "graph": graph}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "component_count": r1.component_count, "dependency_count": r1.dependency_count,
            "health_count": r1.health_count}
