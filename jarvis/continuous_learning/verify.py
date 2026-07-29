"""Continuous Learning 검증 (P20) — 체인·변조·중복·생애주기·참조·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 기억/교훈 생애주기 전이 합법성(genesis 시작). 중복
기억/교훈(genesis 유일). 참조 무결성(모든 레코드 source_reference 존재). 계보(dangling·순환). **변경 없음.**
"""
from __future__ import annotations

from jarvis.continuous_learning import ledger
from jarvis.continuous_learning import models as M
from jarvis.continuous_learning.models import GENESIS, content_hash, detect_cycle_check


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


def _lifecycle(records, group_key, initial, can_fn) -> dict:
    issues: list = []
    for gid, evs in sorted(_group(records, group_key).items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != initial:
                    issues.append(f"bad_initial:{gid}:{to}")
            elif not can_fn(prev, to):
                issues.append(f"invalid_transition:{gid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def lifecycle_integrity() -> dict:
    checks = {
        "memory": _lifecycle(ledger.read_memory_events(), "memory_id", M.M_CREATED,
                             M.can_memory_transition),
        "lesson": _lifecycle(ledger.read_lesson_events(), "lesson_id", M.L_DRAFT,
                             M.can_lesson_transition),
    }
    return {"ok": all(v["ok"] for v in checks.values()), "checks": checks}


def duplicate_integrity() -> dict:
    """중복 기억/교훈: genesis 이벤트 유일."""
    issues: list = []
    for records, id_key in ((ledger.read_memory_events(), "memory_id"),
                            (ledger.read_lesson_events(), "lesson_id")):
        seen: set = set()
        for ev in records:
            if ev.get("from_state") == GENESIS:
                gid = ev.get(id_key)
                if gid in seen:
                    issues.append(f"duplicate:{id_key}:{gid}")
                seen.add(gid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def lesson_review_integrity() -> dict:
    """RECORDED 교훈은 검토자(reviewer)를 보유해야 한다(사람 검토 필수)."""
    issues: list = []
    for les in ledger.lesson_ids():
        evs = ledger.lesson_events(les)
        last = evs[-1]
        if last.get("to_state") == M.L_RECORDED and not last.get("reviewer"):
            issues.append(f"recorded_without_reviewer:{les}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 모든 레코드가 source_reference 필드를 보유(빈 문자열 허용)."""
    issues: list = []
    checks = [
        (ledger.read_experiments(), "experiment_memory_id"),
        (ledger.read_failures(), "failure_id"),
        (ledger.read_patterns(), "pattern_id"),
        (ledger.read_metrics(), "metric_id"),
    ]
    for records, idf in checks:
        for r in records:
            if "source_reference" not in r:
                issues.append(f"missing_source_reference:{r.get(idf)}")
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
    lifecycle = lifecycle_integrity()
    duplicate = duplicate_integrity()
    lesson_review = lesson_review_integrity()
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and lesson_review["ok"] and reference["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "lesson_review": lesson_review, "reference": reference,
            "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "memory_event_count": r1.memory_event_count, "failure_count": r1.failure_count}
