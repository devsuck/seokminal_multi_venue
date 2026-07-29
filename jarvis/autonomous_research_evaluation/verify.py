"""Autonomous Research Evaluation 검증 (P12.5) — 체인·변조·중복·생애주기·차원·참조·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 평가 생애주기 전이 합법성(CREATED 시작). 중복
평가(genesis 유일). 차원 유효성(점수/기준의 차원). 참조 무결성(점수/벤치마크의 평가 존재). 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.autonomous_research_evaluation import ledger
from jarvis.autonomous_research_evaluation.models import (
    EVAL_DIMENSIONS,
    E_CREATED,
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


def _by_evaluation() -> dict:
    out: dict = {}
    for ev in ledger.read_evaluation_events():
        out.setdefault(ev.get("evaluation_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """평가 생애주기 전이 합법성(순차, CREATED 시작)."""
    issues: list = []
    for eid, evs in sorted(_by_evaluation().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != E_CREATED:
                    issues.append(f"bad_initial:{eid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{eid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 평가: 같은 evaluation_id 의 CREATED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_evaluation_events():
        if ev.get("from_state") == GENESIS:
            eid = ev.get("evaluation_id")
            if eid in genesis_seen:
                issues.append(f"duplicate_evaluation:{eid}")
            genesis_seen.add(eid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def dimension_integrity() -> dict:
    """차원 유효성: 점수/기준의 차원이 등록된 6개 중 하나."""
    issues: list = []
    for s in ledger.read_scores():
        if s.get("dimension") not in EVAL_DIMENSIONS:
            issues.append(f"invalid_score_dimension:{s.get('score_id')}")
    for c in ledger.read_criteria():
        if c.get("dimension") not in EVAL_DIMENSIONS:
            issues.append(f"invalid_criterion_dimension:{c.get('criterion_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 점수/벤치마크의 평가가 존재하는지."""
    issues: list = []
    eids = set(ledger.evaluation_ids())
    for s in ledger.read_scores():
        if s.get("evaluation_id") not in eids:
            issues.append(f"orphan_score:{s.get('score_id')}")
    for b in ledger.read_benchmarks():
        if b.get("eval_a") not in eids or b.get("eval_b") not in eids:
            issues.append(f"orphan_benchmark:{b.get('benchmark_id')}")
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
    dimension = dimension_integrity()
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and dimension["ok"] and reference["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "dimension": dimension, "reference": reference,
            "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "evaluation_event_count": r1.evaluation_event_count,
            "score_count": r1.score_count}
