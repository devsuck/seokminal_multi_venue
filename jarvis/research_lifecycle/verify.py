"""Research Lifecycle 검증 (P10.26) — 체인·변조·중복·스테이지 전이·타임라인·계보·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 프로젝트: 이벤트 소싱 스테이지 전이 유효성·
연속성(from=이전 to). 아티팩트 계보: dangling parent·순환. **변경/실행/배포/승인/거래 없음.**
"""
from __future__ import annotations

from jarvis.research_lifecycle import ledger
from jarvis.research_lifecycle.models import (
    GENESIS,
    STAGE_TRANSITIONS,
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


def stage_timeline_validation() -> dict:
    """프로젝트 스테이지 타임라인: from/to 연결·전이 유효성(스테이지 건너뛰기 탐지)."""
    issues: list = []
    by_group: dict = {}
    for r in ledger.read_project_events():
        by_group.setdefault(r.get("project_id"), []).append(r)
    for pid, evs in by_group.items():
        expected_from = ""
        for e in evs:
            frm, to = e.get("from_stage", ""), e.get("to_stage", "")
            if frm != expected_from:
                issues.append(f"broken_timeline:{pid}:from{frm}")
            if to not in STAGE_TRANSITIONS.get(frm, set()):
                issues.append(f"invalid_transition:{pid}:{frm or 'GENESIS'}->{to}")
            expected_from = to
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
    timeline = stage_timeline_validation()
    lineage = lineage_validation()
    ok = ok and timeline["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "timeline": timeline, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "project_count": r1.project_count, "transition_count": r1.transition_count,
            "bottleneck_count": r1.bottleneck_count}
