"""P9.6 Operational Audit & Compliance 테스트. **감사 전용.**

이벤트 수집(다중소스·결정순서·중복방지)·operator action·config snapshot·findings(kill-no-recovery/
incident-open-long/failed-approval/chain-broken)·compliance report·verify(체인/변조/중복)·replay·
CLI·보안(금지import·집행/브로커/킬 없음·소스 무변이·append-only·읽기전용).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

from jarvis.operational_audit import ledger
from jarvis.operational_audit import models as M
from jarvis.operational_audit.engine import OperationalAuditEngine
from jarvis.operational_audit.models import CRITICAL, INFO, WARNING
from jarvis.operational_audit.verify import _generic_content_hash

TS0 = "2026-07-23T00:00:00Z"
TS1 = "2026-07-23T00:01:00Z"
TS2 = "2026-07-23T00:02:00Z"
TS_LATE = "2026-07-25T00:00:00Z"   # TS0 로부터 2일 후


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.operational_audit.ledger.state_path", sp)
    return sp


def _w(sp, name, rows):
    with open(sp(name), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _seal_content(rows):
    prev = "GENESIS"
    out = []
    for r in rows:
        r = dict(r)
        r["previous_hash"] = prev
        h = _generic_content_hash(r)
        r["record_hash"] = h
        prev = h
        out.append(r)
    return out


def _seal_linkage(rows, hash_field="report_hash"):
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


def _eng():
    return OperationalAuditEngine()


# ── 1~5. models 순수 ──
def test_severity_rank():
    assert M.severity_rank(CRITICAL) > M.severity_rank(WARNING) > M.severity_rank(INFO)


def test_compliance_score_pure():
    assert M.compliance_score(0, 0, 0) == 100
    assert M.compliance_score(1, 0, 0) == 66
    assert M.compliance_score(0, 1, 0) == 92
    assert M.compliance_score(0, 0, 1) == 98
    assert M.compliance_score(3, 0, 0) == 0   # 하한 clamp


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p1", "record_hash": "r1", "report_hash": "q1"}
    b = {"x": 1, "previous_hash": "p2", "record_hash": "r2", "report_hash": "q2"}
    assert M.content_hash(a) == M.content_hash(b)


def test_finding_id_deterministic():
    assert M.finding_id("rule", "subj") == M.finding_id("rule", "subj")
    assert M.finding_id("rule", "subj").startswith("FND:")


def test_audit_event_id_deterministic():
    assert M.audit_event_id("f.jsonl", "X1") == M.audit_event_id("f.jsonl", "X1")


# ── 6~12. 이벤트 수집 ──
def _seed_health(sp, status="HEALTHY", ts=TS0):
    _w(sp, "system_health_reports.jsonl",
       _seal_linkage([{"report_id": "SHR:1", "overall_status": status, "health_score": 100.0,
                       "timestamp": ts}]))


def test_collect_events_multi_source(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp, ts=TS0)
    _w(sp, "alerts.jsonl", _seal_content([{"alert_id": "A1", "severity": "WARNING",
                                           "source": "X", "timestamp": TS1}]))
    _w(sp, "emergency_decisions.jsonl", _seal_content([{"decision_id": "EMG:1",
                    "emergency_state": "NORMAL", "previous_state": "NORMAL", "timestamp": TS2}]))
    events = _eng().collect_events()
    cats = {e.category for e in events}
    assert {"health", "operations", "emergency"} <= cats
    assert len(events) == 3


def test_collect_events_health_category(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp, "CRITICAL")
    e = _eng().collect_events()[0]
    assert e.category == "health" and e.event_type == "health_state" and e.severity == "CRITICAL"


def test_collect_events_incident_detail(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "incidents.jsonl", _seal_content([{"event_id": "IEV:1", "incident_id": "INC:1",
                    "from_state": "", "to_state": "OPEN", "severity": "CRITICAL", "timestamp": TS0}]))
    e = _eng().collect_events()[0]
    assert e.event_type == "incident_lifecycle" and "INC:1" in e.detail and "OPEN" in e.detail


def test_collect_events_deterministic_order(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "alerts.jsonl", _seal_content([{"alert_id": "A1", "severity": "INFO",
                    "source": "X", "timestamp": TS2}]))
    _seed_health(sp, ts=TS0)
    events = _eng().collect_events()
    ts = [e.timestamp for e in events]
    assert ts == sorted(ts)


def test_collect_events_append_only(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp)
    _eng().collect_events(commit=True)
    assert len(ledger.read_audit_events()) == 1


def test_collect_events_duplicate_prevention(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp)
    eng = _eng()
    eng.collect_events(commit=True)
    eng.collect_events(commit=True)   # 동일 소스 → event_id 동일 → 중복 방지
    assert len(ledger.read_audit_events()) == 1


def test_collect_events_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().collect_events() == []


# ── 13~17. Operator actions ──
def test_operator_action_from_attestation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_attestations.jsonl", _seal_content([{"attestation_id": "RATT:1",
                    "operator_id": "cio", "incident_id": "INC:1", "decision": "REJECT",
                    "timestamp": TS0}]))
    a = _eng().collect_operator_actions()[0]
    assert a.operator_id == "cio" and a.action == "attestation" and a.decision == "REJECT"


def test_operator_action_from_approval(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_approvals.jsonl", _seal_content([{"approval_id": "RCVA:1",
                    "approver": "boss", "request_id": "RCVQ:1", "approved": False, "timestamp": TS0}]))
    a = _eng().collect_operator_actions()[0]
    assert a.action == "recovery_approval" and a.decision == "rejected"


def test_operator_action_from_request(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_requests.jsonl", _seal_content([{"request_id": "RCVQ:1",
                    "requested_by": "op", "from_state": "KILL_ACTIVE", "timestamp": TS0}]))
    a = _eng().collect_operator_actions()[0]
    assert a.action == "recovery_request" and a.operator_id == "op"


def test_operator_actions_append_only(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_attestations.jsonl", _seal_content([{"attestation_id": "RATT:1",
                    "operator_id": "cio", "incident_id": "INC:1", "decision": "REJECT",
                    "timestamp": TS0}]))
    _eng().collect_operator_actions(commit=True)
    assert len(ledger.read_operator_actions()) == 1


def test_operator_actions_duplicate_prevention(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_attestations.jsonl", _seal_content([{"attestation_id": "RATT:1",
                    "operator_id": "cio", "incident_id": "INC:1", "decision": "REJECT",
                    "timestamp": TS0}]))
    eng = _eng()
    eng.collect_operator_actions(commit=True)
    eng.collect_operator_actions(commit=True)
    assert len(ledger.read_operator_actions()) == 1


# ── 18~20. Config snapshot ──
def test_config_snapshot_captures_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().config_snapshot(TS0)
    assert s.autonomy_level == 5 and s.min_live_level == 6
    assert s.live_enabled is False and s.forbidden_count == 6


def test_config_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().config_snapshot(TS0)
    b = _eng().config_snapshot(TS1)   # 다른 시각·동일 config
    assert a.snapshot_id == b.snapshot_id


def test_config_snapshot_append_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.config_snapshot(TS0, commit=True)
    eng.config_snapshot(TS1, commit=True)   # 동일 config → 중복 방지
    assert len(ledger.read_config_snapshots()) == 1


# ── 21~30. Findings ──
def test_finding_kill_active_no_recovery(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", _seal_content([{"decision_id": "EMG:1",
                    "emergency_state": "KILL_ACTIVE", "previous_state": "KILL_PENDING",
                    "timestamp": TS0}]))
    fs = _eng().build_findings(TS0)
    assert any(f.rule == "kill_active_no_recovery" and f.severity == WARNING for f in fs)


def test_finding_kill_active_with_recovery_ok(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", _seal_content([{"decision_id": "EMG:1",
                    "emergency_state": "KILL_ACTIVE", "previous_state": "KILL_PENDING",
                    "timestamp": TS0}]))
    _w(sp, "recovery_requests.jsonl", _seal_content([{"request_id": "RCVQ:1",
                    "requested_by": "op", "timestamp": TS1}]))   # kill 이후 복구 기록
    fs = _eng().build_findings(TS1)
    assert not any(f.rule == "kill_active_no_recovery" for f in fs)


def test_finding_incident_open_long(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "incidents.jsonl", _seal_content([{"event_id": "IEV:1", "incident_id": "INC:1",
                    "to_state": "OPEN", "severity": "CRITICAL", "timestamp": TS0}]))
    fs = _eng().build_findings(TS_LATE)   # 2일 경과
    assert any(f.rule == "incident_open_long" and f.severity == WARNING for f in fs)


def test_finding_incident_recent_none(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "incidents.jsonl", _seal_content([{"event_id": "IEV:1", "incident_id": "INC:1",
                    "to_state": "OPEN", "severity": "CRITICAL", "timestamp": TS0}]))
    fs = _eng().build_findings(TS1)   # 1분 경과
    assert not any(f.rule == "incident_open_long" for f in fs)


def test_finding_incident_closed_none(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "incidents.jsonl", _seal_content([
        {"event_id": "IEV:1", "incident_id": "INC:1", "to_state": "OPEN", "severity": "CRITICAL",
         "timestamp": TS0},
        {"event_id": "IEV:2", "incident_id": "INC:1", "to_state": "CLOSED", "severity": "CRITICAL",
         "timestamp": TS1}]))
    fs = _eng().build_findings(TS_LATE)
    assert not any(f.rule == "incident_open_long" for f in fs)


def test_finding_failed_recovery_approval(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_approvals.jsonl", _seal_content([{"approval_id": "RCVA:1",
                    "approver": "boss", "approved": False, "timestamp": TS0}]))
    fs = _eng().build_findings(TS0)
    assert any(f.rule == "failed_recovery_approval" and f.severity == INFO for f in fs)


def test_finding_rejected_recovery_event(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_events.jsonl", _seal_content([{"event_id": "RCVE:1",
                    "outcome": "rejected", "timestamp": TS0}]))
    fs = _eng().build_findings(TS0)
    assert any(f.rule == "failed_recovery_approval" and f.severity == INFO for f in fs)


def test_finding_hash_chain_broken_critical(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    rows = _seal_content([{"alert_id": "A1", "severity": "WARNING", "source": "X", "timestamp": TS0},
                          {"alert_id": "A2", "severity": "INFO", "source": "Y", "timestamp": TS1}])
    rows[1]["previous_hash"] = "sha256:deadbeef"   # 체인 손상
    _w(sp, "alerts.jsonl", rows)
    fs = _eng().build_findings(TS0)
    assert any(f.rule == "hash_chain_broken" and f.severity == CRITICAL for f in fs)


def test_findings_sorted_by_severity(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    rows = _seal_content([{"alert_id": "A1", "severity": "INFO", "source": "X", "timestamp": TS0}])
    rows.append(dict(rows[0]))   # 중복 → 체인 깨짐 → CRITICAL
    _w(sp, "alerts.jsonl", rows)
    _w(sp, "recovery_approvals.jsonl", _seal_content([{"approval_id": "RCVA:1",
                    "approver": "b", "approved": False, "timestamp": TS0}]))
    fs = _eng().build_findings(TS0)
    assert fs[0].severity == CRITICAL   # 최심각 우선


def test_findings_deduplicated(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "recovery_approvals.jsonl", _seal_content([{"approval_id": "RCVA:1",
                    "approver": "b", "approved": False, "timestamp": TS0}]))
    fs = _eng().build_findings(TS0)
    ids = [f.finding_id for f in fs]
    assert len(ids) == len(set(ids))


# ── 31~38. Compliance report ──
def test_compliance_report_shape(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().audit(TS0)["report"]
    for k in ("audit_period", "event_count", "critical_findings", "warning_findings",
              "info_findings", "chain_status", "compliance_score"):
        assert k in rep.to_dict()


def test_compliance_report_event_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp, ts=TS0)
    rep = _eng().audit(TS0)["report"]
    assert rep.event_count == 1


def test_compliance_report_finding_counts(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", _seal_content([{"decision_id": "EMG:1",
                    "emergency_state": "KILL_ACTIVE", "previous_state": "KILL_PENDING",
                    "timestamp": TS0}]))
    rep = _eng().audit(TS0)["report"]
    assert rep.warning_findings >= 1   # kill_active_no_recovery


def test_compliance_report_chain_intact(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp)
    _w(sp, "alerts.jsonl", _seal_content([{"alert_id": "A1", "severity": "INFO",
                    "source": "X", "timestamp": TS0}]))
    rep = _eng().audit(TS0)["report"]
    assert rep.chain_status == "intact"


def test_compliance_report_chain_broken(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    rows = _seal_content([{"alert_id": "A1", "severity": "INFO", "source": "X", "timestamp": TS0}])
    rows.append(dict(rows[0]))
    _w(sp, "alerts.jsonl", rows)
    rep = _eng().audit(TS0)["report"]
    assert rep.chain_status == "broken" and rep.critical_findings >= 1


def test_compliance_report_score_deducts(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", _seal_content([{"decision_id": "EMG:1",
                    "emergency_state": "KILL_ACTIVE", "previous_state": "KILL_PENDING",
                    "timestamp": TS0}]))
    rep = _eng().audit(TS0)["report"]
    assert rep.compliance_score < 100


def test_compliance_report_audit_period(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp, ts=TS0)
    _w(sp, "alerts.jsonl", _seal_content([{"alert_id": "A1", "severity": "INFO",
                    "source": "X", "timestamp": TS2}]))
    rep = _eng().audit(TS_LATE)["report"]
    assert rep.audit_period["start"] == TS0 and rep.audit_period["end"] == TS2


def test_compliance_report_append_dedup(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp)
    eng = _eng()
    eng.audit(TS0, commit=True)
    eng.audit(TS0, commit=True)
    assert len(ledger.read_compliance_reports()) == 1


# ── 39~45. Verify / tamper / replay ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.operational_audit.verify import verify_chain
    res = verify_chain()
    assert res["ok"] and res["n"] == 0


def test_verify_chain_intact_after_audit(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp)
    from jarvis.operational_audit.verify import verify_chain
    _eng().audit(TS0, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 3   # events + config + compliance


def test_verify_detects_audit_event_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp)
    from jarvis.operational_audit.verify import verify_chain
    _eng().audit(TS0, commit=True)
    path = sp("audit_events.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["severity"] = "CRITICAL"
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    res = verify_chain()
    assert res["ledgers"]["audit_events.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "alerts.jsonl", _seal_content([{"alert_id": "A1", "severity": "INFO",
                    "source": "X", "timestamp": TS0},
                    {"alert_id": "A2", "severity": "INFO", "source": "Y", "timestamp": TS1}]))
    from jarvis.operational_audit.verify import verify_chain
    _eng().audit(TS0, commit=True)
    path = sp("audit_events.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = verify_chain()
    assert res["ledgers"]["audit_events.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp)
    from jarvis.operational_audit.verify import verify_chain
    _eng().audit(TS0, commit=True)
    path = sp("audit_events.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    res = verify_chain()
    assert res["ledgers"]["audit_events.jsonl"]["reason"] in {"duplicate_id",
                                                              "previous_hash_broken"}


def test_verify_source_chains_detects_broken(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    rows = _seal_content([{"alert_id": "A1", "severity": "INFO", "source": "X", "timestamp": TS0}])
    rows[0]["severity"] = "CRITICAL"   # 콘텐츠 변조
    _w(sp, "alerts.jsonl", rows)
    from jarvis.operational_audit.verify import verify_source_chains
    res = verify_source_chains()
    assert res["alerts.jsonl"]["ok"] is False


def test_replay_deterministic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _w(sp, "emergency_decisions.jsonl", _seal_content([{"decision_id": "EMG:1",
                    "emergency_state": "KILL_ACTIVE", "previous_state": "KILL_PENDING",
                    "timestamp": TS0}]))
    from jarvis.operational_audit.verify import replay
    res = replay(_eng(), TS0)
    assert res["deterministic"] is True


# ── 46~49. CLI ──
def test_cli_audit(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.operational_audit.__main__ import main
    assert main(["audit"]) == 0
    assert "compliance_score" in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.operational_audit.__main__ import main
    assert main(["summary"]) == 0
    assert "audit_events" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.operational_audit.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.operational_audit.__main__ import main
    assert main(["replay"]) == 0
    assert "deterministic" in capsys.readouterr().out


# ── 50~58. 보안/읽기전용 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "broker_readonly", _j + "portfolio", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operational_audit.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operational_audit.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", "route_order",
                       ".buy(", ".sell(", "disarm(", "restart_service", "LiveExecutionEngine"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_kill_or_recovery_control():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operational_audit.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "send_order", "kill_switch(",
                       "request_recovery(", "approve_recovery(", "set_kill", "engage_kill"):
            assert banned not in src, f"{m} has control verb {banned}"


def test_read_only_source_no_mutation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp)
    _w(sp, "emergency_decisions.jsonl", _seal_content([{"decision_id": "EMG:1",
                    "emergency_state": "KILL_ACTIVE", "previous_state": "KILL_PENDING",
                    "timestamp": TS0}]))
    src_files = ["system_health_reports.jsonl", "emergency_decisions.jsonl"]
    before = {f: hashlib.sha256(open(sp(f), "rb").read()).hexdigest() for f in src_files}
    _eng().audit(TS0, commit=True)
    after = {f: hashlib.sha256(open(sp(f), "rb").read()).hexdigest() for f in src_files}
    assert before == after   # 소스 원장 무변이


def test_append_only_never_deletes(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_health(sp, ts=TS0)
    eng = _eng()
    eng.audit(TS0, commit=True)
    n1 = len(ledger.read_audit_events())
    _w(sp, "alerts.jsonl", _seal_content([{"alert_id": "A1", "severity": "INFO",
                    "source": "X", "timestamp": TS1}]))
    eng.audit(TS0, commit=True)
    assert len(ledger.read_audit_events()) > n1   # 오직 증가


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6   # P9.6 는 권한 정책에 아무것도 추가하지 않음
    # P9.6 고유 액션명이 정책에 유입되지 않았는지(권한 확장 없음)
    for kw in ("operational_audit", "compliance_report", "audit_override", "audit_disable"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_ledger_source_reader_no_write_to_source():
    # 소스 리더는 read 만 — 소스 원장에 append 함수 없음
    import inspect
    from jarvis.operational_audit import ledger as L
    src = inspect.getsource(L)
    assert "append_source" not in src and "write_source" not in src


def test_report_has_no_control_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().audit(TS0)["report"]
    keys = set(rep.to_dict())
    for f in ("order_id", "kill_switch", "authorize", "execute", "enable_live", "disarm"):
        assert f not in keys


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
