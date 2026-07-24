"""Research Memory System 검증 (P11.12) — 체인·변조·중복·생애주기·참조·연관계보·스냅샷 일관성·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(손상·변조) + id 중복(중복 기억 id). 기억 생애주기 전이 합법성
(CREATED 시작). 참조 무결성: 지식/맥락/실험/실패/패턴/연관/카탈로그가 알려진 기억을 참조하는지(invalid reference).
연관 계보: 순환(circular association). 스냅샷 일관성: 저장된 memory_count == 재계산. **변경/실행/승인/수정 없음.**
"""
from __future__ import annotations

from jarvis.research_memory_system import ledger
from jarvis.research_memory_system.models import (
    GENESIS,
    M_CREATED,
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


def lifecycle_integrity() -> dict:
    """기억별 생애주기 전이 합법성(순차, CREATED 시작)."""
    issues: list = []
    by_mem: dict = {}
    for ev in ledger.read_memory_events():
        by_mem.setdefault(ev.get("memory_id"), []).append(ev)
    for mem, evs in sorted(by_mem.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M_CREATED:
                    issues.append(f"bad_initial:{mem}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"illegal:{mem}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 기억 id 탐지: 같은 memory_id 의 CREATED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_memory_events():
        if ev.get("from_state") == GENESIS:
            mem = ev.get("memory_id")
            if mem in genesis_seen:
                issues.append(f"duplicate_memory:{mem}")
            genesis_seen.add(mem)
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 파생 레코드/카탈로그가 알려진 기억을 참조하는지(invalid reference)."""
    issues: list = []
    ids = set(ledger.memory_ids())
    checks = [
        (ledger.read_registry(), "registry_id", "memory_id", "registry"),
        (ledger.read_knowledge(), "knowledge_id", "memory_id", "knowledge"),
        (ledger.read_contexts(), "context_id", "memory_id", "context"),
        (ledger.read_experiments(), "experiment_memory_id", "memory_id", "experiment"),
        (ledger.read_failures(), "failure_memory_id", "memory_id", "failure"),
        (ledger.read_patterns(), "success_pattern_id", "memory_id", "pattern"),
    ]
    for recs, idf, ref_field, label in checks:
        for r in recs:
            if r.get(ref_field) not in ids:
                issues.append(f"invalid_ref_{label}:{r.get(idf)}")
    for a in ledger.read_associations():
        if a.get("memory_a") not in ids:
            issues.append(f"invalid_ref_assoc_a:{a.get('association_id')}")
        if a.get("memory_b") not in ids:
            issues.append(f"invalid_ref_assoc_b:{a.get('association_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def association_integrity() -> dict:
    """연관 계보: 순환 연관(circular association) 탐지."""
    issues: list = []
    edges = [(a.get("memory_a"), a.get("memory_b")) for a in ledger.read_associations()]
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("circular_association:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): dangling·순환."""
    issues: list = []
    arts = ledger.read_artifacts()
    aids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in aids:
                issues.append(f"dangling_artifact:{a.get('artifact_id')}")
            edges.append((a.get("artifact_id"), parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("cycle_artifact:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def snapshot_consistency() -> dict:
    """스냅샷 일관성: 저장된 memory_count == 분포 합계."""
    issues: list = []
    for s in ledger.read_snapshots():
        dist_sum = sum((s.get("state_distribution") or {}).values())
        if dist_sum != s.get("memory_count"):
            issues.append(f"inconsistent_snapshot:{s.get('snapshot_id')}")
        tdist_sum = sum((s.get("type_distribution") or {}).values())
        if tdist_sum != s.get("memory_count"):
            issues.append(f"inconsistent_type_snapshot:{s.get('snapshot_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lifecycle = lifecycle_integrity()
    duplicate = duplicate_integrity()
    reference = reference_integrity()
    association = association_integrity()
    lineage = lineage_integrity()
    snapshot = snapshot_consistency()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and reference["ok"] and association["ok"]
          and lineage["ok"] and snapshot["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "reference": reference, "association": association,
            "lineage": lineage, "snapshot": snapshot}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "memory_event_count": r1.memory_event_count,
            "association_count": r1.association_count,
            "search_count": r1.search_count}
