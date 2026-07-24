"""Research Learning Loop 검증 (P12.8) — 체인·변조·중복·생애주기·판정·개선불변·참조·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 루프 생애주기 전이 합법성(OBSERVED 시작). 중복
루프(genesis 유일). 판정 유효성. 개선 후보 applied=False 강제(자동 적용 금지). 참조 무결성. 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_learning import ledger
from jarvis.research_learning.models import (
    OBS_VERDICTS,
    L_OBSERVED,
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


def _by_loop() -> dict:
    out: dict = {}
    for ev in ledger.read_loop_events():
        out.setdefault(ev.get("loop_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """루프 생애주기 전이 합법성(순차, OBSERVED 시작)."""
    issues: list = []
    for lid, evs in sorted(_by_loop().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != L_OBSERVED:
                    issues.append(f"bad_initial:{lid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{lid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 루프: 같은 loop_id 의 OBSERVED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_loop_events():
        if ev.get("from_state") == GENESIS:
            lid = ev.get("loop_id")
            if lid in genesis_seen:
                issues.append(f"duplicate_loop:{lid}")
            genesis_seen.add(lid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def verdict_integrity() -> dict:
    """판정 유효성: 관찰의 판정이 등록된 값."""
    issues: list = []
    for o in ledger.read_observations():
        if o.get("verdict") not in OBS_VERDICTS:
            issues.append(f"invalid_verdict:{o.get('observation_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def no_auto_apply_integrity() -> dict:
    """자동 적용 금지: 모든 개선 후보는 applied=False 여야 한다(자동 개선 없음)."""
    issues: list = []
    for imp in ledger.read_improvements():
        if imp.get("applied") is not False:
            issues.append(f"improvement_applied:{imp.get('improvement_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 관찰/교훈/개선/피드백/패턴의 루프가 존재하는지."""
    issues: list = []
    lids = set(ledger.loop_ids())
    checks = [
        (ledger.read_observations(), "observation_id", "observation"),
        (ledger.read_lessons(), "lesson_id", "lesson"),
        (ledger.read_improvements(), "improvement_id", "improvement"),
        (ledger.read_feedback(), "feedback_id", "feedback"),
    ]
    for recs, idf, label in checks:
        for r in recs:
            if r.get("loop_id") not in lids:
                issues.append(f"orphan_{label}:{r.get(idf)}")
    for p in ledger.read_patterns():
        if p.get("loop_a") not in lids or p.get("loop_b") not in lids:
            issues.append(f"orphan_pattern:{p.get('pattern_id')}")
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
    verdict = verdict_integrity()
    no_auto = no_auto_apply_integrity()
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and verdict["ok"] and no_auto["ok"]
          and reference["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "verdict": verdict, "no_auto_apply": no_auto,
            "reference": reference, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "loop_event_count": r1.loop_event_count, "lesson_count": r1.lesson_count}
