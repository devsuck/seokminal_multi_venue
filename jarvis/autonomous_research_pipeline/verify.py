"""Autonomous Research Pipeline 검증 (P12.1) — 체인·변조·중복·전이·아티팩트·고아사이클·참조·이력·계보. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 스테이지 전이 합법성(GENESIS→OBJECTIVE_CREATED
시작·유효 선형 전이만 — invalid stage transition). 아티팩트 존재(missing artifacts). 고아 사이클(objective 부재·전이
부재). 참조 일관성(런/이력/스테이지의 cycle 존재·목표의 파이프라인). 이력 손상. 중복 사이클 id. **변경 없음.**
"""
from __future__ import annotations

from jarvis.autonomous_research_pipeline import ledger
from jarvis.autonomous_research_pipeline.models import (
    ART_CYCLE,
    GENESIS,
    S_OBJECTIVE_CREATED,
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


def transition_integrity() -> dict:
    """스테이지 전이 합법성(순차, GENESIS→OBJECTIVE_CREATED 시작) — invalid stage transition 탐지."""
    issues: list = []
    by_cycle: dict = {}
    for tr in ledger.read_transitions():
        by_cycle.setdefault(tr.get("cycle_id"), []).append(tr)
    for cid, trs in sorted(by_cycle.items()):
        prev = None
        for tr in trs:
            frm, to = tr.get("from_stage"), tr.get("to_stage")
            if prev is None:
                if frm != GENESIS or to != S_OBJECTIVE_CREATED:
                    issues.append(f"bad_initial:{cid}:{frm}->{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{cid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def cycle_integrity() -> dict:
    """고아 사이클(objective 부재·전이 부재) + 중복 사이클 id."""
    issues: list = []
    oids = {o.get("objective_id") for o in ledger.read_objectives()}
    seen: set = set()
    for c in ledger.read_cycles():
        cid = c.get("cycle_id")
        if cid in seen:
            issues.append(f"duplicate_cycle:{cid}")
        seen.add(cid)
        if c.get("objective_id") not in oids:
            issues.append(f"orphan_cycle_objective:{cid}")
        if not ledger.cycle_transitions(cid):
            issues.append(f"orphan_cycle_no_transition:{cid}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def artifact_presence() -> dict:
    """아티팩트 존재: 모든 사이클은 CYCLE 아티팩트를 가진다(missing artifacts)."""
    issues: list = []
    art_refs = {(a.get("artifact_type"), a.get("ref_id")) for a in ledger.read_artifacts()}
    for c in ledger.read_cycles():
        if (ART_CYCLE, c.get("cycle_id")) not in art_refs:
            issues.append(f"missing_artifact:{c.get('cycle_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 일관성: 런/이력/스테이지의 cycle_id, 목표의 pipeline_id 가 존재하는지(inconsistent references)."""
    issues: list = []
    cids = set(ledger.cycle_ids())
    pids = {p.get("pipeline_id") for p in ledger.read_pipelines()}
    for o in ledger.read_objectives():
        if o.get("pipeline_id") not in pids:
            issues.append(f"inconsistent_objective_pipeline:{o.get('objective_id')}")
    for r in ledger.read_runs():
        if r.get("cycle_id") not in cids:
            issues.append(f"inconsistent_run_cycle:{r.get('run_id')}")
    for s in ledger.read_stages():
        if s.get("cycle_id") not in cids:
            issues.append(f"inconsistent_stage_cycle:{s.get('stage_id')}")
    for h in ledger.read_history():
        if h.get("cycle_id") not in cids:
            issues.append(f"corrupted_history_cycle:{h.get('history_id')}")
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
    transition = transition_integrity()
    cycle = cycle_integrity()
    artifact = artifact_presence()
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = (ok and transition["ok"] and cycle["ok"] and artifact["ok"] and reference["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "transition": transition, "cycle": cycle,
            "artifact": artifact, "reference": reference, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "cycle_count": r1.cycle_count, "transition_count": r1.transition_count,
            "history_count": r1.history_count}
