"""Knowledge Intelligence 검증 (P10.27) — 체인·변조·중복·그래프 무결성·계보·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 그래프: 클러스터 멤버 중복·모순 subject
중복. 아티팩트 계보: dangling parent·순환. **변경/실행/선택/승인/배포 없음.**
"""
from __future__ import annotations

from jarvis.knowledge_intelligence import ledger
from jarvis.knowledge_intelligence.models import (
    GENESIS,
    content_hash,
    detect_cycle,
    members_hash as _members_hash,
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


def graph_integrity() -> dict:
    """지식 그래프 무결성: 클러스터 members_hash 일관성·멤버 중복, 유사도 자기참조."""
    issues: list = []
    for c in ledger.read_clusters():
        members = c.get("members", [])
        if _members_hash(members) != c.get("members_hash"):
            issues.append(f"cluster_members_hash_mismatch:{c.get('cluster_id')}")
        if len(members) != len(set(members)):
            issues.append(f"cluster_duplicate_member:{c.get('cluster_id')}")
        if c.get("size") != len(members):
            issues.append(f"cluster_size_mismatch:{c.get('cluster_id')}")
    for s in ledger.read_similarity():
        if s.get("ref_a") == s.get("ref_b"):
            issues.append(f"self_similarity:{s.get('similarity_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_validation() -> dict:
    """아티팩트 계보(parent 체인): dangling parent·순환 탐지."""
    issues: list = []
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"dangling:{a.get('artifact_id')}->{parent}")
            edges.append((a.get("artifact_id"), parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("lineage_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    graph = graph_integrity()
    lineage = lineage_validation()
    ok = ok and graph["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "graph": graph, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "insight_count": r1.insight_count, "cluster_count": r1.cluster_count,
            "similarity_count": r1.similarity_count}
