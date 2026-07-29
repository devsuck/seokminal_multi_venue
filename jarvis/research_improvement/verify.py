"""Research Improvement 검증 (P11.10) — 체인·변조·중복·생애주기·참조·학습 계보·아티팩트 계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 개선 생애주기 전이 합법성(OBSERVED 시작).
중복 개선 기록 탐지(같은 improvement_id 의 genesis 이벤트는 유일). 참조 무결성: 소스 계층 지정 시 소스 참조 필수
(누락 탐지). 학습 계보: dangling 부모·순환 의존성. 아티팩트 계보: dangling·순환. **변경/실행/승인/수정 없음.**
"""
from __future__ import annotations

from jarvis.research_improvement import ledger
from jarvis.research_improvement.models import (
    GENESIS,
    I_OBSERVED,
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
    """개선별 생애주기 전이 합법성(순차, OBSERVED 시작)."""
    issues: list = []
    by_imp: dict = {}
    for ev in ledger.read_improvement_events():
        by_imp.setdefault(ev.get("improvement_id"), []).append(ev)
    for imp, evs in sorted(by_imp.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != I_OBSERVED:
                    issues.append(f"bad_initial:{imp}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"illegal:{imp}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 개선 기록 탐지: 같은 improvement_id 의 genesis(OBSERVED) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: dict = {}
    for ev in ledger.read_improvement_events():
        if ev.get("from_state") == GENESIS:
            imp = ev.get("improvement_id")
            desc = ev.get("description")
            if imp in genesis_seen:
                issues.append(f"duplicate_genesis:{imp}")
            genesis_seen[imp] = desc
    # 같은 (cycle,category,title)→improvement_id 는 결정적이므로 서로 다른 description 은 곧 충돌.
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """소스 참조 무결성: source_layer 가 있으나 source_ref 가 없는 레코드(누락) 탐지."""
    issues: list = []
    for o in ledger.read_observations():
        if o.get("source_layer") and not o.get("source_ref"):
            issues.append(f"missing_source_observation:{o.get('observation_id')}")
    for f in ledger.read_failures():
        if f.get("source_layer") and not f.get("source_ref"):
            issues.append(f"missing_source_failure:{f.get('failure_id')}")
    for lr in ledger.read_learning():
        if lr.get("source_layer") and not lr.get("source_ref"):
            issues.append(f"missing_source_learning:{lr.get('learning_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def learning_lineage_integrity() -> dict:
    """학습 계보(parent_learning): dangling 부모·순환 의존성 탐지."""
    issues: list = []
    recs = ledger.read_learning()
    ids = {r.get("learning_id") for r in recs}
    edges: list = []
    for r in recs:
        parent = r.get("parent_learning")
        if parent:
            if parent not in ids:
                issues.append(f"dangling_learning:{r.get('learning_id')}")
            edges.append((r.get("learning_id"), parent))
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("cycle_learning:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): dangling·순환."""
    issues: list = []
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
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
    reference = reference_integrity()
    learning = learning_lineage_integrity()
    lineage = lineage_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and reference["ok"]
          and learning["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "reference": reference, "learning": learning,
            "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "cycle_count": r1.cycle_count,
            "improvement_event_count": r1.improvement_event_count,
            "learning_count": r1.learning_count}
