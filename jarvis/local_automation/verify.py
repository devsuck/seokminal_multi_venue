"""Local Automation 검증 (P45) — 체인·중복·잡 생애주기·실행 안전·스케줄·재현. 읽기전용."""
from __future__ import annotations

from jarvis.local_automation import ledger
from jarvis.local_automation import models as M
from jarvis.local_automation.models import GENESIS, content_hash


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


def job_lifecycle_integrity() -> dict:
    issues = []
    for jid, evs in sorted(_group(ledger.read_job_events(), "job_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.J_REGISTERED:
                    issues.append(f"bad_initial:{jid}:{to}")
            elif not M.can_job_transition(prev, to):
                issues.append(f"invalid_transition:{jid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def job_kind_integrity() -> dict:
    """등록된 모든 잡 종류는 허용목록 안이고 금지(거래·배포·배분) 종류가 없어야 한다."""
    issues = []
    for ev in ledger.read_job_events():
        if ev.get("from_state") == GENESIS:
            kind = ev.get("kind")
            if M.is_forbidden_job_kind(kind):
                issues.append(f"forbidden_kind:{ev.get('job_id')}:{kind}")
            elif kind not in M.JOB_KINDS:
                issues.append(f"unknown_kind:{ev.get('job_id')}:{kind}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def run_safety_integrity() -> dict:
    """모든 실행은 is_binding=False 이고 상태는 알려진 집합이어야 한다(자동 거래/배포 없음)."""
    issues = []
    job_ids = set(ledger.job_ids())
    for r in ledger.read_runs():
        if r.get("is_binding") is not False:
            issues.append(f"binding_run:{r.get('run_id')}")
        if r.get("status") not in M.RUN_STATUSES:
            issues.append(f"bad_status:{r.get('run_id')}")
        if r.get("job_id") not in job_ids:
            issues.append(f"orphan_run:{r.get('run_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def schedule_integrity() -> dict:
    issues = []
    job_ids = set(ledger.job_ids())
    for s in ledger.read_schedules():
        if s.get("cadence") not in M.CADENCES:
            issues.append(f"bad_cadence:{s.get('schedule_id')}")
        if s.get("job_id") not in job_ids:
            issues.append(f"orphan_schedule:{s.get('schedule_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues = []
    seen = set()
    for ev in ledger.read_job_events():
        if ev.get("from_state") == GENESIS:
            jid = ev.get("job_id")
            if jid in seen:
                issues.append(f"duplicate_job:{jid}")
            seen.add(jid)
    s2 = set()
    for r in ledger.read_runs():
        rid = r.get("run_id")
        if rid in s2:
            issues.append(f"duplicate_run:{rid}")
        s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lifecycle = job_lifecycle_integrity()
    kind = job_kind_integrity()
    run = run_safety_integrity()
    sched = schedule_integrity()
    dup = duplicate_integrity()
    ok = (ok and lifecycle["ok"] and kind["ok"] and run["ok"] and sched["ok"] and dup["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "job_lifecycle": lifecycle,
            "job_kind": kind, "run_safety": run, "schedule": sched, "duplicate": dup}


def replay(engine, now="") -> dict:
    s1 = engine.summary(now)
    s2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": s1.to_dict() == s2.to_dict() and p1.to_dict() == p2.to_dict(),
            "job_count": s1.job_count, "run_count": s1.run_count}
