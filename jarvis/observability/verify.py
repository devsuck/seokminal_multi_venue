"""Observability 검증 (P17) — 체인·변조·중복·건강 생애주기·참조·알림·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 건강 생애주기 전이 합법성(UNKNOWN 시작). 중복
대상(genesis 유일). 참조 무결성(지표/가용성→대상). 알림 무결성(is_actionable=False). 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.observability import ledger
from jarvis.observability.models import (
    H_UNKNOWN,
    GENESIS,
    can_transition,
    content_hash,
    detect_cycle_check,
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


def _by_target() -> dict:
    out: dict = {}
    for ev in ledger.read_health_events():
        out.setdefault(ev.get("target_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """건강 생애주기 전이 합법성(순차, UNKNOWN 시작)."""
    issues: list = []
    for tid, evs in sorted(_by_target().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != H_UNKNOWN:
                    issues.append(f"bad_initial:{tid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{tid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 대상: 같은 target_id 의 UNKNOWN(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_health_events():
        if ev.get("from_state") == GENESIS:
            tid = ev.get("target_id")
            if tid in genesis_seen:
                issues.append(f"duplicate_target:{tid}")
            genesis_seen.add(tid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 가용성 레코드의 target_id 가 존재하는지."""
    issues: list = []
    tids = set(ledger.target_ids())
    for a in ledger.read_availability():
        if a.get("target_id") not in tids:
            issues.append(f"orphan_availability:{a.get('availability_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def alert_integrity() -> dict:
    """알림 무결성: 모든 알림 is_actionable=False (자동 조치 금지)."""
    issues: list = []
    for a in ledger.read_alerts():
        if a.get("is_actionable") is not False:
            issues.append(f"actionable_alert:{a.get('alert_id')}")
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
    reference = reference_integrity()
    alert = alert_integrity()
    lineage = lineage_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and reference["ok"] and alert["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "reference": reference, "alert": alert, "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "health_event_count": r1.health_event_count, "metric_count": r1.metric_count}
