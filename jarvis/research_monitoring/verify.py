"""Research Monitoring 검증 (P23) — 체인·중복·세션 생애주기·이상(자동조치 금지)·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 세션 생애주기 전이 합법성(CREATED 시작). 중복 세션
(genesis 유일). 이상 무결성(is_actionable=False). 아티팩트 계보(missing parent·broken reference·순환). **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_monitoring import ledger
from jarvis.research_monitoring import models as M
from jarvis.research_monitoring.models import GENESIS, content_hash, detect_cycle_check


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


def session_lifecycle_integrity() -> dict:
    """세션 생애주기 전이 합법성(CREATED 시작)."""
    issues: list = []
    for sid, evs in sorted(_group(ledger.read_session_events(), "session_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.S_CREATED:
                    issues.append(f"bad_initial:{sid}:{to}")
            elif not M.can_session_transition(prev, to):
                issues.append(f"invalid_transition:{sid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 세션: 같은 session_id 의 CREATED(genesis) 이벤트는 유일 + 스냅샷/리포트 id 유일."""
    issues: list = []
    seen: set = set()
    for ev in ledger.read_session_events():
        if ev.get("from_state") == GENESIS:
            sid = ev.get("session_id")
            if sid in seen:
                issues.append(f"duplicate_session:{sid}")
            seen.add(sid)
    for records, idf, label in ((ledger.read_snapshots(), "snapshot_id", "snapshot"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def anomaly_integrity() -> dict:
    """이상 무결성: 모든 이상 is_actionable=False (탐지·기록만, 자동 조치 금지)."""
    issues: list = []
    for a in ledger.read_anomalies():
        if a.get("is_actionable") is not False:
            issues.append(f"actionable_anomaly:{a.get('anomaly_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """참조 무결성: 헬스 체크 상태 유효 + 지표 유형 유효."""
    issues: list = []
    for h in ledger.read_health_checks():
        if h.get("status") not in M.HEALTH_STATUSES:
            issues.append(f"invalid_health_status:{h.get('health_id')}")
    for m in ledger.read_metrics():
        if m.get("metric_type") not in M.METRIC_TYPES:
            issues.append(f"invalid_metric_type:{m.get('metric_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): missing parent·broken reference·순환."""
    issues: list = []
    arts = ledger.read_artifacts()
    aids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in aids:
                issues.append(f"missing_parent:{a.get('artifact_id')}")
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
    session = session_lifecycle_integrity()
    duplicate = duplicate_integrity()
    anomaly = anomaly_integrity()
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = (ok and session["ok"] and duplicate["ok"] and anomaly["ok"] and reference["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "session_lifecycle": session,
            "duplicate": duplicate, "anomaly": anomaly, "reference": reference, "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약/스냅샷 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    s1 = engine.create_snapshot("SYSTEM", now, commit=False)
    s2 = engine.create_snapshot("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and s1.to_dict() == s2.to_dict(),
            "metric_count": r1.metric_count, "anomaly_count": r1.anomaly_count}
