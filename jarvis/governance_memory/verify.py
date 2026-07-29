"""Governance Memory 검증 (P10.21) — 체인·변조·중복·링크·계보·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 링크: 미등록 노드 참조·유형·derived_from
순환. 계보: 아티팩트 dangling parent·순환. 중복 지식 항목(content_hash 기반). **변경/실행/승인/배포 없음.**
"""
from __future__ import annotations

from jarvis.governance_memory import ledger
from jarvis.governance_memory.models import (
    ACYCLIC_LINK_TYPES,
    GENESIS,
    LINK_TYPES,
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


def _known_refs() -> set:
    refs: set = set()
    refs.update(r.get("entry_id") for r in ledger.read_entries())
    refs.update(r.get("experience_id") for r in ledger.read_experiences())
    refs.update(r.get("lesson_id") for r in ledger.read_lessons())
    refs.update(r.get("resolution_id") for r in ledger.read_resolutions())
    return refs


def link_validation() -> dict:
    """링크 무결성: 유형·미등록 노드 참조(dangling)·자기참조·derived_from 순환."""
    issues: list = []
    known = _known_refs()
    for l in ledger.read_links():
        if l.get("link_type") not in LINK_TYPES:
            issues.append(f"invalid_link_type:{l.get('link_id')}")
        ft, tt = l.get("from_ref"), l.get("to_ref")
        if ft == tt:
            issues.append(f"self_link:{l.get('link_id')}")
        if known and ft not in known:
            issues.append(f"dangling_reference:{l.get('link_id')}:{ft}")
        if known and tt not in known:
            issues.append(f"dangling_reference:{l.get('link_id')}:{tt}")
    edges = [(l.get("from_ref"), l.get("to_ref")) for l in ledger.read_links()
             if l.get("link_type") in ACYCLIC_LINK_TYPES]
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("link_cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_links": len(ledger.read_links())}


def duplicate_entry_validation() -> dict:
    """중복 지식 항목: 동일 entry_id 가 두 번 이상 나타나면 위반(append-only 무결성)."""
    issues: list = []
    seen: set = set()
    for e in ledger.read_entries():
        eid = e.get("entry_id")
        if eid in seen:
            issues.append(f"duplicate_entry:{eid}")
        seen.add(eid)
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
    link = link_validation()
    duplicate = duplicate_entry_validation()
    lineage = lineage_validation()
    ok = ok and link["ok"] and duplicate["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "link": link, "duplicate": duplicate,
            "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "entry_count": r1.entry_count, "lesson_count": r1.lesson_count,
            "link_count": r1.link_count}
