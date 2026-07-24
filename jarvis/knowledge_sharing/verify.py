"""Knowledge Sharing 검증 (P11.8) — 체인·변조·중복·엔트리 생애주기·참조/계보 무결성·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 엔트리 생애주기 전이 합법성. 링크/계보:
dangling·순환. **변경/실행/승인/상위수정 없음.**
"""
from __future__ import annotations

from jarvis.knowledge_sharing import ledger
from jarvis.knowledge_sharing.models import (
    DIRECTIONAL_LINKS,
    GENESIS,
    K_CREATED,
    LINK_ENTRY_RELATED,
    LINK_ENTRY_TOPIC,
    LINK_TOPIC_PARENT,
    LINK_TOPIC_RELATED,
    can_transition,
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


def entry_lifecycle_integrity() -> dict:
    """엔트리별 생애주기 전이 합법성(순차)."""
    issues: list = []
    by_entry: dict = {}
    for ev in ledger.read_entry_events():
        by_entry.setdefault(ev.get("entry_id"), []).append(ev)
    for eid, evs in sorted(by_entry.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != K_CREATED:
                    issues.append(f"bad_initial:{eid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"illegal:{eid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """링크 참조 무결성: dangling(토픽/엔트리 미존재)·자기참조."""
    issues: list = []
    tids = {t.get("topic_id") for t in ledger.read_topics()}
    eids = set(ledger.entry_ids())
    for l in ledger.read_links():
        lt, s, t = l.get("link_type"), l.get("source_id"), l.get("target_id")
        if s == t:
            issues.append(f"self:{l.get('link_id')}")
        if lt in (LINK_TOPIC_PARENT, LINK_TOPIC_RELATED):
            if s not in tids or t not in tids:
                issues.append(f"dangling_topic:{l.get('link_id')}")
        elif lt == LINK_ENTRY_RELATED:
            if s not in eids or t not in eids:
                issues.append(f"dangling_entry:{l.get('link_id')}")
        elif lt == LINK_ENTRY_TOPIC:
            if s not in eids or t not in tids:
                issues.append(f"dangling_entry_topic:{l.get('link_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def cycle_integrity() -> dict:
    """방향성 링크(토픽 부모·엔트리 파생) 순환 없음."""
    issues: list = []
    for lt in DIRECTIONAL_LINKS:
        edges = [(l.get("source_id"), l.get("target_id")) for l in ledger.links_of_type(lt)]
        cyc = detect_cycle(edges)
        if cyc:
            issues.append(f"cycle:{lt}:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """지식 계보(child→parent): dangling·순환."""
    issues: list = []
    eids = set(ledger.entry_ids())
    edges: list = []
    for r in ledger.read_lineage():
        child, parent = r.get("child_entry"), r.get("parent_entry")
        if child not in eids or parent not in eids:
            issues.append(f"dangling:{r.get('lineage_id')}")
        edges.append((child, parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def artifact_lineage_integrity() -> dict:
    """아티팩트 계보(parent): dangling·순환."""
    issues: list = []
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"dangling:{a.get('artifact_id')}")
            edges.append((a.get("artifact_id"), parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lifecycle = entry_lifecycle_integrity()
    reference = reference_integrity()
    cycle = cycle_integrity()
    lineage = lineage_integrity()
    art_lineage = artifact_lineage_integrity()
    ok = ok and lifecycle["ok"] and reference["ok"] and cycle["ok"] and lineage["ok"] and \
        art_lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "reference": reference, "cycle": cycle, "lineage": lineage,
            "artifact_lineage": art_lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약·스냅샷 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    s1 = engine.snapshot_knowledge("REPLAY", now, commit=False)
    s2 = engine.snapshot_knowledge("REPLAY", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict()
            and s1.content_digest == s2.content_digest,
            "entry_count": r1.entry_event_count, "transfer_count": r1.transfer_count,
            "content_digest": s1.content_digest}
