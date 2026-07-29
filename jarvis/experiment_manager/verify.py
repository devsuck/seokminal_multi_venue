"""Experiment Manager 검증 (P11.4) — 체인·변조·중복·생애주기·거래승인 경계·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 실험별 생애주기 전이 합법성. 거래승인 경계:
어떤 연구 요청/리포트도 trading_approval=True 를 갖지 않는다(연구 승인 ≠ 거래 승인). **변경/실행/배포 없음.**
"""
from __future__ import annotations

from jarvis.experiment_manager import ledger
from jarvis.experiment_manager.models import (
    EXP_PROPOSED,
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


def lifecycle_integrity() -> dict:
    """실험별 생애주기 전이 합법성(순차)."""
    issues: list = []
    by_exp: dict = {}
    for ev in ledger.read_experiment_events():
        by_exp.setdefault(ev.get("experiment_id"), []).append(ev)
    for exp, evs in sorted(by_exp.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != EXP_PROPOSED:
                    issues.append(f"bad_initial:{exp}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"illegal:{exp}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def trading_approval_boundary() -> dict:
    """거래 승인 경계: 연구 요청·리포트 어느 것도 trading_approval=True 가 아님."""
    issues: list = []
    for r in ledger.read_requests():
        if r.get("trading_approval", False):
            issues.append(f"request_trading_approval:{r.get('request_id')}")
        if not r.get("research_only", False):
            issues.append(f"request_not_research_only:{r.get('request_id')}")
    for r in ledger.read_reports():
        if r.get("trading_approval", False):
            issues.append(f"report_trading_approval:{r.get('report_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lifecycle = lifecycle_integrity()
    boundary = trading_approval_boundary()
    ok = ok and lifecycle["ok"] and boundary["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "trading_boundary": boundary}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "experiment_count": r1.experiment_count, "plan_count": r1.plan_count,
            "result_count": r1.result_count}
