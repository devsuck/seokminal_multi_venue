"""Research Memory Intelligence 검증 (P27) — 체인·중복·메모리 생애주기·진화(추가전용)·패턴·검색(추천금지)·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 메모리 생애주기(CREATED 시작). 중복 메모리(genesis
유일). 진화 무결성(change_type 유효·알려진 메모리 참조). 검색 무결성(is_recommendation=False). 패턴 무결성(유형 유효).
아티팩트 계보(missing parent·broken reference·순환). **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_memory_intelligence import ledger
from jarvis.research_memory_intelligence import models as M
from jarvis.research_memory_intelligence.models import GENESIS, content_hash, detect_cycle_check


def _verify_records(records, id_field) -> dict:
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


def _group(records, key) -> dict:
    out: dict = {}
    for r in records:
        out.setdefault(r.get(key), []).append(r)
    return out


def memory_lifecycle_integrity() -> dict:
    """메모리 생애주기 전이 합법성(CREATED 시작)."""
    issues: list = []
    for mid, evs in sorted(_group(ledger.read_memory_events(), "memory_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.M_CREATED:
                    issues.append(f"bad_initial:{mid}:{to}")
            elif not M.can_memory_transition(prev, to):
                issues.append(f"invalid_transition:{mid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 방지: 메모리 genesis 유일 + 패턴/교훈/성공/실패/리포트 id 유일."""
    issues: list = []
    seen: set = set()
    for ev in ledger.read_memory_events():
        if ev.get("from_state") == GENESIS:
            mid = ev.get("memory_id")
            if mid in seen:
                issues.append(f"duplicate_memory:{mid}")
            seen.add(mid)
    for records, idf, label in ((ledger.read_patterns(), "pattern_id", "pattern"),
                                (ledger.read_lessons(), "lesson_id", "lesson"),
                                (ledger.read_successes(), "success_id", "success"),
                                (ledger.read_failures(), "failure_id", "failure"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def evolution_integrity() -> dict:
    """진화 무결성: change_type 유효 + 알려진 메모리 참조(추가전용 append 로만)."""
    issues: list = []
    mem_ids = set(ledger.memory_ids())
    for e in ledger.read_evolution_events():
        if e.get("change_type") not in M.CHANGE_TYPES:
            issues.append(f"invalid_change_type:{e.get('event_id')}")
        if e.get("memory_id") not in mem_ids:
            issues.append(f"orphan_evolution:{e.get('event_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def pattern_integrity() -> dict:
    """패턴 무결성: 패턴 유형 유효."""
    issues: list = []
    for p in ledger.read_patterns():
        if p.get("pattern_type") not in M.PATTERN_TYPES:
            issues.append(f"invalid_pattern_type:{p.get('pattern_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def retrieval_integrity() -> dict:
    """검색 무결성: 모든 검색 is_recommendation=False(참조만·자동 추천/선택 금지)."""
    issues: list = []
    for r in ledger.read_retrievals():
        if r.get("is_recommendation") is not False:
            issues.append(f"recommendation_retrieval:{r.get('retrieval_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): missing parent·broken reference·순환. Entity→Memory→Lesson→Pattern."""
    issues: list = []
    arts = ledger.read_artifacts()
    aids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in aids:
                issues.append(f"missing_parent:{a.get('artifact_id')}")
            edges.append((a.get("artifact_id"), parent))
    if detect_cycle_check(edges):
        issues.append("cycle_artifact")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    memory = memory_lifecycle_integrity()
    duplicate = duplicate_integrity()
    evolution = evolution_integrity()
    pattern = pattern_integrity()
    retrieval = retrieval_integrity()
    lineage = lineage_integrity()
    ok = (ok and memory["ok"] and duplicate["ok"] and evolution["ok"] and pattern["ok"]
          and retrieval["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "memory_lifecycle": memory,
            "duplicate": duplicate, "evolution": evolution, "pattern": pattern,
            "retrieval": retrieval, "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약/검색 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    q1 = engine.retrieve_context("regime robustness", 5, now, commit=False)
    q2 = engine.retrieve_context("regime robustness", 5, now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and q1.to_dict() == q2.to_dict(),
            "memory_count": r1.memory_count, "retrieval_refs": q1.memory_refs}
