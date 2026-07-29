"""Research Knowledge Graph 검증 (P10.5) — 체인 무결성·변조·중복·리플레이·순환·고아 검증. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 관계·계보: 순환 의존 탐지 ·
미존재 엔티티 참조(깨진 계보) · 고아 탐지. replay: 동일 상태 리포트 재계산 → 동일 산출.
**변경/배분/실행/배포 없음.**
"""
from __future__ import annotations

from jarvis.research_kg import ledger
from jarvis.research_kg.models import GENESIS, content_hash, detect_cycle


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
    """관계 순환·계보 순환·깨진 계보(미존재 엔티티)·고아 엔티티 검증."""
    issues: list = []
    entity_ids = {e.get("entity_id") for e in ledger.distinct_entities()}

    rels = ledger.read_relationships()
    for r in rels:
        for ref in (r.get("source_entity"), r.get("target_entity")):
            if ref not in entity_ids:
                issues.append(f"dangling_relationship:{r.get('relationship_id')}:{ref}")
    rel_edges = [(r.get("source_entity"), r.get("target_entity")) for r in rels]
    cyc = detect_cycle(rel_edges)
    if cyc:
        issues.append("relationship_cycle:" + "->".join(cyc))

    lineage = ledger.read_lineage_edges()
    for e in lineage:
        for ref in (e.get("from_entity"), e.get("to_entity")):
            if ref not in entity_ids:
                issues.append(f"broken_lineage:{e.get('lineage_id')}:{ref}")
    lin_edges = [(e.get("from_entity"), e.get("to_entity")) for e in lineage]
    lcyc = detect_cycle(lin_edges)
    if lcyc:
        issues.append("lineage_cycle:" + "->".join(lcyc))

    # 아티팩트 계보 dangling parent
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    for a in arts:
        parent = a.get("parent_artifact")
        if parent and parent not in ids:
            issues.append(f"broken_artifact_lineage:{a.get('artifact_id')}->{parent}")

    return {"ok": not issues, "issues": sorted(set(issues)),
            "n_entities": len(entity_ids), "n_relationships": len(rels)}


def orphan_report() -> dict:
    """관계에 참여하지 않는 고아 엔티티(정보용 — 결함 아님)."""
    entity_ids = {e.get("entity_id") for e in ledger.distinct_entities()}
    touched: set = set()
    for r in ledger.read_relationships():
        touched.add(r.get("source_entity"))
        touched.add(r.get("target_entity"))
    orphans = sorted(entity_ids - touched)
    return {"n_orphans": len(orphans), "orphans": orphans}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    graph = graph_validation()
    ok = ok and graph["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "graph": graph,
            "orphans": orphan_report()}


def replay(engine, now: str = "") -> dict:
    """동일 상태 그래프 리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.generate_graph_report(now)
    r2 = engine.generate_graph_report(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "total_entities": r1.total_entities,
            "entity_distribution": r1.entity_distribution,
            "research_clusters": r1.research_clusters}
