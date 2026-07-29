"""P9.5 Operations Control Center 테스트. **읽기전용 시각화·관제 뷰.**

dashboard(empty/healthy/critical·집계)·timeline(다중소스·시간정렬·중복방지·결정성)·emergency(전
상태 표시·무변이)·recovery(준비도·실패체크)·audit(체인상태·변조탐지)·render·CLI·보안(금지import·
집행/브로커/게이트웨이 없음·원장쓰기함수 없음·상태변이/신규파일 없음·킬/복구제어 없음·읽기전용).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

from jarvis.operations_console import ledger
from jarvis.operations_console.engine import OperationsConsole, render_dashboard
from jarvis.operations_console.models import NO_DATA
from jarvis.operations_console.verify import _content_hash

TS0 = "2026-07-23T00:00:00Z"
TS1 = "2026-07-23T00:01:00Z"
TS2 = "2026-07-23T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.operations_console.ledger.state_path", sp)
    return sp


def _w(sp, name, rows):
    with open(sp(name), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _seal_content(rows):
    """P9.2/9.3/9.4 record_hash 스킴으로 체인 봉인(감사 검증 통과용)."""
    prev = "GENESIS"
    out = []
    for r in rows:
        r = dict(r)
        r["previous_hash"] = prev
        h = _content_hash(r)
        r["record_hash"] = h
        prev = h
        out.append(r)
    return out


def _seal_linkage(rows, hash_field="report_hash"):
    """P9.1 report_hash 스킴(링크만) 봉인."""
    prev = "GENESIS"
    out = []
    for i, r in enumerate(rows):
        r = dict(r)
        r["previous_hash"] = prev
        h = f"sha256:hh{i:04d}"
        r[hash_field] = h
        prev = h
        out.append(r)
    return out


def _health_row(status="HEALTHY", score=100.0, total=17, unhealthy=0, degraded=None, ts=TS0,
                rid="SHR:1"):
    return {"report_id": rid, "overall_status": status, "health_score": score,
            "summary": {"total": total, "healthy": total - unhealthy, "unhealthy": unhealthy,
                        "degraded": degraded or []}, "timestamp": ts}


def _incident_row(inc="INC:1", ev="IEV:1", to="OPEN", sev="CRITICAL", ts=TS0, frm=""):
    return {"incident_id": inc, "event_id": ev, "to_state": to, "from_state": frm,
            "severity": sev, "timestamp": ts, "alert_key": f"{inc}|{sev}"}


def _emergency_row(state="NORMAL", prev="NORMAL", ts=TS0, did="EMG:1"):
    return {"decision_id": did, "emergency_state": state, "previous_state": prev,
            "source": "assess", "reasons": [], "timestamp": ts}


def _readiness_row(status="READY", mand=None, warns=None, ts=TS0, rid="RRR:1"):
    return {"report_id": rid, "overall_status": status, "mandatory_failures": mand or [],
            "warnings": warns or [], "evidence_hash": "sha256:e", "checklist_hash": "sha256:c",
            "emergency_state": "NORMAL", "timestamp": ts}


def _attest_row(op="op", dec="APPROVE_RESTART_REVIEW", ts=TS0, aid="RATT:1"):
    return {"attestation_id": aid, "operator_id": op, "decision": dec,
            "readiness_status": "READY", "timestamp": ts}


def _eng():
    return OperationsConsole()


# ── 1~11. Dashboard / aggregation ──
def test_empty_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    snap = _eng().snapshot(TS0)
    assert snap.health_summary["overall_status"] == NO_DATA
    assert snap.incident_summary["active_total"] == 0
    assert snap.emergency_state == NO_DATA
    assert snap.recovery_status["readiness"] == NO_DATA
    assert snap.audit_status["ok"] is True   # 빈 체인 = ok


def test_healthy_state(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "system_health_reports.jsonl", [_health_row("HEALTHY")])
    _w(sp, "emergency_decisions.jsonl", [_emergency_row("NORMAL")])
    _w(sp, "recovery_readiness.jsonl", [_readiness_row("READY")])
    ov = _eng().system_overview()
    assert ov["overall_health"] == "HEALTHY"
    assert ov["emergency_state"] == "NORMAL"
    assert ov["recovery_readiness"] == "READY"
    assert ov["active_incidents"] == 0


def test_critical_state(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "system_health_reports.jsonl", [_health_row("CRITICAL", score=0.0, unhealthy=3,
                                                       degraded=["X", "Y", "Z"])])
    _w(sp, "incidents.jsonl", [_incident_row(sev="CRITICAL", to="OPEN")])
    _w(sp, "emergency_decisions.jsonl", [_emergency_row("KILL_ACTIVE", prev="KILL_PENDING")])
    _w(sp, "recovery_readiness.jsonl", [_readiness_row("FAILED", mand=["HEALTH_NO_CRITICAL"])])
    ov = _eng().system_overview()
    assert ov["overall_health"] == "CRITICAL"
    assert ov["incident_critical"] == 1
    assert ov["emergency_state"] == "KILL_ACTIVE"
    assert ov["recovery_readiness"] == "FAILED"


def test_health_summary_aggregation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "system_health_reports.jsonl", [_health_row("WARNING", total=17, unhealthy=2,
                                                       degraded=["A", "B"])])
    hs = _eng().health_summary()
    assert hs["total"] == 17 and hs["unhealthy"] == 2 and hs["healthy"] == 15
    assert hs["degraded"] == ["A", "B"]


def test_alert_summary_counts(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "alerts.jsonl", [
        {"alert_id": "A1", "severity": "WARNING", "source": "X", "timestamp": TS0},
        {"alert_id": "A2", "severity": "CRITICAL", "source": "Y", "timestamp": TS1},
        {"alert_id": "A3", "severity": "WARNING", "source": "Z", "timestamp": TS2}])
    a = _eng().alert_summary()
    assert a["WARNING"] == 2 and a["CRITICAL"] == 1 and a["total"] == 3


def test_incident_summary_active_fold(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "incidents.jsonl", [
        _incident_row("INC:1", "IEV:1", "OPEN", "CRITICAL"),
        _incident_row("INC:2", "IEV:2", "OPEN", "WARNING")])
    isum = _eng().incident_summary()
    assert isum["CRITICAL"] == 1 and isum["WARNING"] == 1 and isum["active_total"] == 2


def test_incident_closed_excluded(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "incidents.jsonl", [
        _incident_row("INC:1", "IEV:1", "OPEN", "CRITICAL", ts=TS0),
        _incident_row("INC:1", "IEV:2", "CLOSED", "CRITICAL", ts=TS1, frm="RESOLVED")])
    isum = _eng().incident_summary()
    assert isum["active_total"] == 0 and isum["tracked_total"] == 1


def test_emergency_state_latest(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", [
        _emergency_row("NORMAL", ts=TS0, did="EMG:1"),
        _emergency_row("SAFE_MODE", prev="NORMAL", ts=TS1, did="EMG:2")])
    assert _eng().emergency_state() == "SAFE_MODE"


def test_recovery_status_fields(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_readiness.jsonl", [_readiness_row("FAILED", mand=["HEALTH_NO_CRITICAL"])])
    _w(sp, "recovery_evidence.jsonl", [{"evidence_id": "REV:1"}, {"evidence_id": "REV:2"}])
    _w(sp, "recovery_attestations.jsonl", [_attest_row("cio", "REJECT")])
    rs = _eng().recovery_status()
    assert rs["readiness"] == "FAILED" and rs["failed_checks"] == ["HEALTH_NO_CRITICAL"]
    assert rs["evidence_count"] == 2
    assert rs["latest_attestation"]["operator_id"] == "cio"
    assert rs["latest_attestation"]["decision"] == "REJECT"


def test_recovery_no_data(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rs = _eng().recovery_status()
    assert rs["readiness"] == NO_DATA and rs["latest_attestation"] is None


def test_system_overview_shape(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ov = _eng().system_overview()
    for k in ("overall_health", "unhealthy_subsystems", "active_incidents",
              "emergency_state", "recovery_readiness"):
        assert k in ov


# ── 12~17. Timeline ──
def _seed_all_sources(sp):
    _w(sp, "system_health_reports.jsonl", [_health_row(ts=TS0, rid="SHR:1")])
    _w(sp, "alerts.jsonl", [{"alert_id": "A1", "severity": "WARNING", "source": "X",
                             "timestamp": TS1}])
    _w(sp, "incidents.jsonl", [_incident_row(ts=TS2)])
    _w(sp, "escalations.jsonl", [{"escalation_id": "ESC:1", "incident_id": "INC:1",
                                  "severity": "CRITICAL", "level": 1, "timestamp": TS2}])
    _w(sp, "emergency_decisions.jsonl", [_emergency_row("KILL_ACTIVE", ts="2026-07-23T00:03:00Z")])
    _w(sp, "recovery_readiness.jsonl", [_readiness_row(ts="2026-07-23T00:04:00Z")])
    _w(sp, "recovery_attestations.jsonl", [_attest_row(ts="2026-07-23T00:05:00Z")])


def test_timeline_multi_source(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_all_sources(sp)
    tl = _eng().timeline()
    sources = {e.source for e in tl}
    assert sources == {"health", "alert", "incident", "escalation", "emergency", "recovery"}
    assert len(tl) == 7


def test_timeline_chronological(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_all_sources(sp)
    tl = _eng().timeline()
    ts = [e.timestamp for e in tl]
    assert ts == sorted(ts)


def test_timeline_deterministic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_all_sources(sp)
    a = [e.to_dict() for e in _eng().timeline()]
    b = [e.to_dict() for e in _eng().timeline()]
    assert a == b


def test_timeline_duplicate_prevention(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "alerts.jsonl", [
        {"alert_id": "A1", "severity": "WARNING", "source": "X", "timestamp": TS0},
        {"alert_id": "A1", "severity": "WARNING", "source": "X", "timestamp": TS0}])  # 중복 id
    tl = _eng().timeline()
    assert len([e for e in tl if e.event_id == "alert:A1"]) == 1


def test_timeline_event_shape(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "incidents.jsonl", [_incident_row()])
    ev = _eng().timeline()[0]
    assert ev.source == "incident" and ev.event_id.startswith("incident:")
    assert "INC:1" in ev.description


def test_timeline_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().timeline() == []


# ── 18~21. Emergency panel ──
def test_emergency_all_states_display(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    for st in ("NORMAL", "WATCH", "SAFE_MODE", "KILL_PENDING", "KILL_ACTIVE",
               "RECOVERY_PENDING", "RECOVERED"):
        _w(sp, "emergency_decisions.jsonl", [_emergency_row(st)])
        assert _eng().emergency_panel()["emergency_state"] == st


def test_emergency_kill_latch_flag(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", [_emergency_row("KILL_ACTIVE")])
    assert _eng().emergency_panel()["kill_latch"] is True


def test_emergency_panel_read_only(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", [_emergency_row("NORMAL")])
    assert _eng().emergency_panel()["read_only"] is True


def test_emergency_no_mutation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", [_emergency_row("KILL_ACTIVE")])
    before = hashlib.sha256(open(sp("emergency_decisions.jsonl"), "rb").read()).hexdigest()
    _eng().dashboard(TS0)
    after = hashlib.sha256(open(sp("emergency_decisions.jsonl"), "rb").read()).hexdigest()
    assert before == after


# ── 22~24. Recovery panel ──
def test_recovery_readiness_display(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_readiness.jsonl", [_readiness_row("WARNING", warns=["INCIDENT_RESOLVED"])])
    rp = _eng().recovery_panel()
    assert rp["readiness"] == "WARNING" and "INCIDENT_RESOLVED" in rp["warnings"]


def test_recovery_failed_checks_display(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_readiness.jsonl", [_readiness_row("FAILED",
                                        mand=["EMERGENCY_NOT_KILL_ACTIVE"])])
    rp = _eng().recovery_panel()
    assert rp["failed_checks"] == ["EMERGENCY_NOT_KILL_ACTIVE"] and rp["read_only"] is True


def test_recovery_latest_attestation_display(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_readiness.jsonl", [_readiness_row("READY")])
    _w(sp, "recovery_attestations.jsonl", [_attest_row("op1", "APPROVE_RESTART_REVIEW")])
    rp = _eng().recovery_panel()
    assert rp["latest_attestation"]["decision"] == "APPROVE_RESTART_REVIEW"


# ── 25~29. Audit panel ──
def test_audit_chain_status_ok(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "alerts.jsonl", _seal_content([
        {"alert_id": "A1", "severity": "WARNING", "source": "X", "timestamp": TS0},
        {"alert_id": "A2", "severity": "CRITICAL", "source": "Y", "timestamp": TS1}]))
    ap = _eng().audit_panel()
    assert ap["chain_ok"] is True
    assert ap["ledgers"]["alerts.jsonl"]["ok"] is True


def test_audit_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    rows = _seal_content([
        {"alert_id": "A1", "severity": "WARNING", "source": "X", "timestamp": TS0},
        {"alert_id": "A2", "severity": "CRITICAL", "source": "Y", "timestamp": TS1}])
    rows[1]["previous_hash"] = "sha256:deadbeef"
    _w(sp, "alerts.jsonl", rows)
    ap = _eng().audit_panel()
    assert ap["chain_ok"] is False
    assert ap["ledgers"]["alerts.jsonl"]["reason"] == "previous_hash_broken"


def test_audit_detects_content_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    rows = _seal_content([{"alert_id": "A1", "severity": "WARNING", "source": "X",
                           "timestamp": TS0}])
    rows[0]["severity"] = "CRITICAL"   # 해시 재계산 없이 콘텐츠 변조
    _w(sp, "alerts.jsonl", rows)
    ap = _eng().audit_panel()
    assert ap["ledgers"]["alerts.jsonl"]["reason"] == "hash_mismatch"


def test_audit_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    rows = _seal_content([{"alert_id": "A1", "severity": "WARNING", "source": "X",
                           "timestamp": TS0}])
    rows.append(dict(rows[0]))   # 동일 id 재기록
    _w(sp, "alerts.jsonl", rows)
    ap = _eng().audit_panel()
    assert ap["ledgers"]["alerts.jsonl"]["reason"] in {"duplicate_id", "previous_hash_broken"}


def test_audit_latest_hashes_present(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "system_health_reports.jsonl", _seal_linkage([_health_row(ts=TS0)]))
    ap = _eng().audit_panel()
    assert ap["latest_hashes"]["system_health_reports.jsonl"] is not None


# ── 30~32. Render ──
def test_render_dashboard_sections(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "system_health_reports.jsonl", [_health_row("HEALTHY")])
    _w(sp, "emergency_decisions.jsonl", [_emergency_row("NORMAL")])
    _w(sp, "recovery_readiness.jsonl", [_readiness_row("READY")])
    txt = render_dashboard(_eng().dashboard(TS0))
    for section in ("System:", "Incidents:", "Emergency:", "Recovery:", "Audit:"):
        assert section in txt
    assert "read-only" in txt


def test_render_shows_counts(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "incidents.jsonl", [_incident_row(sev="CRITICAL")])
    txt = render_dashboard(_eng().dashboard(TS0))
    assert "CRITICAL:1" in txt and "WARNING:0" in txt


def test_render_shows_kill_latch(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", [_emergency_row("KILL_ACTIVE")])
    txt = render_dashboard(_eng().dashboard(TS0))
    assert "KILL LATCH" in txt


# ── 33~36. CLI ──
def test_cli_dashboard(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.operations_console.__main__ import main
    assert main(["dashboard"]) == 0
    assert "System:" in capsys.readouterr().out


def test_cli_status(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.operations_console.__main__ import main
    assert main(["status"]) == 0
    assert "emergency_state" in capsys.readouterr().out


def test_cli_timeline(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.operations_console.__main__ import main
    assert main(["timeline"]) == 0
    assert "events" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.operations_console.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


# ── 37~38. 결정성/리플레이 ──
def test_snapshot_deterministic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_all_sources(sp)
    assert _eng().snapshot(TS0).to_dict() == _eng().snapshot(TS0).to_dict()


def test_dashboard_deterministic_replay(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_all_sources(sp)
    assert _eng().dashboard(TS0).to_dict() == _eng().dashboard(TS0).to_dict()


# ── 39~46. 보안/읽기전용 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "portfolio", _j + "risk.governor", _j + "broker_readonly")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operations_console.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operations_console.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", "route_order",
                       ".buy(", ".sell(", "disarm(", "restart_service", "LiveExecutionEngine"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_gateway():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operations_console.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "send_order",
                       "create_order", "reconnect(", "kill_switch("):
            assert banned not in src, f"{m} has broker/gateway/kill verb {banned}"


def test_ledger_has_no_write_functions():
    import inspect
    from jarvis.operations_console import ledger as L
    src = inspect.getsource(L)
    assert "def append" not in src and "def write" not in src
    assert '"a")' not in src and '"w")' not in src   # 파일 append/write 모드 없음


def test_no_state_mutation_no_new_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_all_sources(sp)
    before = {f: hashlib.sha256(open(os.path.join(tmp_path, f), "rb").read()).hexdigest()
              for f in os.listdir(tmp_path)}
    eng = _eng()
    eng.dashboard(TS0)
    eng.timeline()
    eng.snapshot(TS0)
    from jarvis.operations_console.verify import verify_all
    verify_all()
    after = {f: hashlib.sha256(open(os.path.join(tmp_path, f), "rb").read()).hexdigest()
             for f in os.listdir(tmp_path)}
    assert before == after   # 신규 파일 없음·기존 무변이


def test_no_kill_or_recovery_control():
    import importlib
    import inspect
    for m in ("engine", "__main__", "models", "verify", "ledger"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operations_console.{m}"))
        for banned in ("request_recovery", "approve_recovery", "attest(", "set_kill",
                       "engage_kill", "release_kill", "transition("):
            assert banned not in src, f"{m} has control verb {banned}"


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("console", "dashboard", "operations_console"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False


def test_ledger_module_read_only_surface():
    # 콘솔 원장 모듈은 read_* 와 latest 만 노출(쓰기 표면 없음)
    for fn in ("read_health", "read_alerts", "read_incidents", "read_escalations",
               "read_emergency", "read_readiness", "read_attestations", "read_evidence"):
        assert hasattr(ledger, fn)
    assert not hasattr(ledger, "append_health") and not hasattr(ledger, "write_health")
