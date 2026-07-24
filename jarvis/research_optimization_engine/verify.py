"""Research Optimization Engine 검증 (P12.6) — 체인·변조·중복·생애주기·제안완결성·심각도·참조·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 연구 생애주기 전이 합법성(OBSERVED 시작). 중복
연구(genesis 유일). 제안 완결성(problem/evidence/impact/risk/reviewer 필수). 심각도 유효성. 참조(병목/효율/제안/
비교의 연구 존재). **변경/실행/자동 최적화 없음.**
"""
from __future__ import annotations

from jarvis.research_optimization_engine import ledger
from jarvis.research_optimization_engine.models import (
    O_OBSERVED,
    SEVERITIES,
    GENESIS,
    can_transition,
    content_hash,
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


def _by_study() -> dict:
    out: dict = {}
    for ev in ledger.read_study_events():
        out.setdefault(ev.get("study_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """연구 생애주기 전이 합법성(순차, OBSERVED 시작)."""
    issues: list = []
    for sid, evs in sorted(_by_study().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != O_OBSERVED:
                    issues.append(f"bad_initial:{sid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{sid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 연구: 같은 study_id 의 OBSERVED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_study_events():
        if ev.get("from_state") == GENESIS:
            sid = ev.get("study_id")
            if sid in genesis_seen:
                issues.append(f"duplicate_study:{sid}")
            genesis_seen.add(sid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def proposal_integrity() -> dict:
    """제안 완결성: problem/evidence/expected_impact/risk/reviewer 필수."""
    issues: list = []
    for p in ledger.read_proposals():
        for field in ("problem", "evidence", "expected_impact", "risk", "reviewer"):
            if not p.get(field):
                issues.append(f"incomplete_proposal:{p.get('proposal_id')}:{field}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def severity_integrity() -> dict:
    """심각도 유효성: 병목의 심각도가 등록된 값."""
    issues: list = []
    for b in ledger.read_bottlenecks():
        if b.get("severity") not in SEVERITIES:
            issues.append(f"invalid_severity:{b.get('bottleneck_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 병목/효율/제안/비교의 연구가 존재하는지."""
    issues: list = []
    sids = set(ledger.study_ids())
    checks = [
        (ledger.read_bottlenecks(), "bottleneck_id", "bottleneck"),
        (ledger.read_efficiency(), "efficiency_id", "efficiency"),
        (ledger.read_proposals(), "proposal_id", "proposal"),
        (ledger.read_comparisons(), "comparison_id", "comparison"),
    ]
    for recs, idf, label in checks:
        for r in recs:
            if r.get("study_id") not in sids:
                issues.append(f"orphan_{label}:{r.get(idf)}")
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
    proposal = proposal_integrity()
    severity = severity_integrity()
    reference = reference_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and proposal["ok"] and severity["ok"]
          and reference["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "proposal": proposal, "severity": severity,
            "reference": reference}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "study_event_count": r1.study_event_count,
            "bottleneck_count": r1.bottleneck_count}
