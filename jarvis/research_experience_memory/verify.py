"""Research Memory & Experience 검증 (P12.7) — 체인·변조·중복·생애주기·유형·참조·에피소드·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 기억 생애주기 전이 합법성(CREATED 시작). 중복
기억(genesis 유일). 유형 유효성. 참조 무결성(경험/실패/패턴의 기억, 에피소드의 기억 참조). 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_experience_memory import ledger
from jarvis.research_experience_memory.models import (
    MEMORY_TYPES,
    M_CREATED,
    GENESIS,
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


def _by_memory() -> dict:
    out: dict = {}
    for ev in ledger.read_memory_events():
        out.setdefault(ev.get("memory_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """기억 생애주기 전이 합법성(순차, CREATED 시작)."""
    issues: list = []
    for mid, evs in sorted(_by_memory().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M_CREATED:
                    issues.append(f"bad_initial:{mid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{mid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 기억: 같은 memory_id 의 CREATED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_memory_events():
        if ev.get("from_state") == GENESIS:
            mid = ev.get("memory_id")
            if mid in genesis_seen:
                issues.append(f"duplicate_memory:{mid}")
            genesis_seen.add(mid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def type_integrity() -> dict:
    """유형 유효성: 기억 유형이 등록된 7개 중 하나."""
    issues: list = []
    for ev in ledger.read_memory_events():
        if ev.get("from_state") == GENESIS and ev.get("memory_type") not in MEMORY_TYPES:
            issues.append(f"invalid_memory_type:{ev.get('memory_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 경험/실패/패턴의 기억, 에피소드의 기억 참조가 존재하는지."""
    issues: list = []
    ids = set(ledger.memory_ids())
    for e in ledger.read_experiences():
        if e.get("memory_id") not in ids:
            issues.append(f"orphan_experience:{e.get('experience_id')}")
    for f in ledger.read_failures():
        if f.get("memory_id") not in ids:
            issues.append(f"orphan_failure:{f.get('failure_id')}")
    for p in ledger.read_patterns():
        if p.get("memory_id") not in ids:
            issues.append(f"orphan_pattern:{p.get('pattern_id')}")
    for ep in ledger.read_episodes():
        for r in ep.get("memory_refs", []):
            if r not in ids:
                issues.append(f"dangling_episode_ref:{ep.get('episode_id')}:{r}")
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


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lifecycle = lifecycle_integrity()
    duplicate = duplicate_integrity()
    typ = type_integrity()
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and typ["ok"] and reference["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "type": typ, "reference": reference, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "memory_event_count": r1.memory_event_count,
            "retrieval_count": r1.retrieval_count}
