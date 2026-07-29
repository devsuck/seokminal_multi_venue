"""Autonomous Research Control Plane 검증 (P12.10) — 체인·변조·중복·생애주기·참조·알림·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 상태 생애주기 전이 합법성(INITIALIZED 시작). 중복
상태(genesis 유일). 참조 무결성(이벤트/헬스/지표/알림→상태). 알림 무결성(is_actionable=False — 자동 조치 없음).
아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_control import ledger
from jarvis.research_control.models import (
    S_INITIALIZED,
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


def _by_state() -> dict:
    out: dict = {}
    for ev in ledger.read_state_events():
        out.setdefault(ev.get("state_id"), []).append(ev)
    return out


def lifecycle_integrity() -> dict:
    """상태 생애주기 전이 합법성(순차, INITIALIZED 시작)."""
    issues: list = []
    for sid, evs in sorted(_by_state().items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != S_INITIALIZED:
                    issues.append(f"bad_initial:{sid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"invalid_transition:{sid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 상태: 같은 state_id 의 INITIALIZED(genesis) 이벤트는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_state_events():
        if ev.get("from_state") == GENESIS:
            sid = ev.get("state_id")
            if sid in genesis_seen:
                issues.append(f"duplicate_state:{sid}")
            genesis_seen.add(sid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 이벤트/헬스/지표/알림의 state_id 가 존재하는지."""
    issues: list = []
    sids = set(ledger.state_ids())
    for e in ledger.read_events():
        if e.get("state_id") not in sids:
            issues.append(f"orphan_event:{e.get('event_id')}")
    for h in ledger.read_health():
        if h.get("state_id") not in sids:
            issues.append(f"orphan_health:{h.get('health_id')}")
    for m in ledger.read_metrics():
        if m.get("state_id") not in sids:
            issues.append(f"orphan_metric:{m.get('metric_id')}")
    for a in ledger.read_alerts():
        if a.get("state_id") not in sids:
            issues.append(f"orphan_alert:{a.get('alert_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def alert_integrity() -> dict:
    """알림 무결성: 모든 알림 is_actionable=False (자동 복구·조치 금지)."""
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
    """동일 상태 스냅샷 두 번 → 동일 산출(결정성). commit 없음."""
    s1 = engine.create_snapshot(now)
    s2 = engine.create_snapshot(now)
    return {"deterministic": s1.to_dict() == s2.to_dict(),
            "state_event_count": s1.state_event_count, "event_count": s1.event_count}
