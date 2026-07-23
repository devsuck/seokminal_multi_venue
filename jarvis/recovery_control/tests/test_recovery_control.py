"""P9.4 Recovery Operations Control 테스트. **복구 관제 전용.**

readiness(healthy READY·critical FAIL·incident FAIL·kill active FAIL·warning WARNING)·evidence(결정
해시·중복방지·append-only)·attestation(승인 체크리스트 필요·반려 기록·중복방지·FAILED 승인차단)·
verify(체인/변조/중복)·replay·CLI·보안(금지import·집행/브로커/게이트웨이 없음·권한/리스크/포트폴리오/
페이퍼/비상 무변이·자동복구 경로 없음).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.recovery_control import ledger
from jarvis.recovery_control import models as M
from jarvis.recovery_control.engine import RecoveryControlEngine
from jarvis.recovery_control.models import (
    APPROVE_RESTART_REVIEW,
    FAILED,
    READY,
    REJECT,
    WARNING,
    RecoveryAttestationError,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.recovery_control.ledger.state_path", sp)
    return sp


def _ready_kw(**over):
    kw = dict(health={"overall_status": "HEALTHY", "subsystems": []}, incidents=[],
              escalations=[], emergency_decisions=[{"emergency_state": "NORMAL"}],
              recovery_requests=[], recovery_events=[], live_enabled=False, live_rows=[])
    kw.update(over)
    return kw


def _crit_inc():
    return [{"incident_id": "INC:1", "to_state": "OPEN", "severity": "CRITICAL"}]


def _warn_inc():
    return [{"incident_id": "INC:2", "to_state": "OPEN", "severity": "WARNING"}]


def _eng():
    return RecoveryControlEngine()


# ── 1~15. Readiness 평가 ──
def test_healthy_system_ready(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw())
    assert r.overall_status == READY
    assert r.mandatory_failures == []


def test_critical_health_fail(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(health={"overall_status": "CRITICAL", "subsystems": []}))
    assert r.overall_status == FAILED
    assert "HEALTH_NO_CRITICAL" in r.mandatory_failures


def test_critical_subsystem_fail(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(health={"overall_status": "WARNING",
                      "subsystems": [{"name": "X", "status": "CRITICAL"}]}))
    assert r.overall_status == FAILED and "HEALTH_NO_CRITICAL" in r.mandatory_failures


def test_offline_health_fail(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(health={"overall_status": "OFFLINE", "subsystems": []}))
    assert r.overall_status == FAILED and "HEALTH_NO_OFFLINE" in r.mandatory_failures


def test_warning_health_generates_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(health={"overall_status": "WARNING", "subsystems": []}))
    assert r.overall_status == WARNING and r.mandatory_failures == []


def test_unresolved_critical_incident_fail(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(incidents=_crit_inc()))
    assert r.overall_status == FAILED and "INCIDENT_NO_ACTIVE_CRITICAL" in r.mandatory_failures


def test_active_noncritical_incident_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(incidents=_warn_inc()))
    assert r.overall_status == WARNING and "INCIDENT_RESOLVED" in r.warnings


def test_escalation_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(incidents=_warn_inc(),
                      escalations=[{"incident_id": "INC:2"}]))
    assert r.overall_status == WARNING and "ESCALATION_CLEAR" in r.warnings


def test_kill_active_blocks_readiness(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(emergency_decisions=[{"emergency_state": "KILL_ACTIVE"}]))
    assert r.overall_status == FAILED
    assert "EMERGENCY_NOT_KILL_ACTIVE" in r.mandatory_failures


def test_kill_pending_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(emergency_decisions=[{"emergency_state": "KILL_PENDING"}]))
    assert r.overall_status == WARNING and "EMERGENCY_STABLE" in r.warnings


def test_safe_mode_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(emergency_decisions=[{"emergency_state": "SAFE_MODE"}]))
    assert r.overall_status == WARNING


def test_live_enabled_fails_boundary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(live_enabled=True))
    assert r.overall_status == FAILED and "LIVE_EXECUTION_DISABLED" in r.mandatory_failures


def test_live_records_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(live_rows=[{"x": 1}]))
    assert r.overall_status == WARNING and "NO_LIVE_EXECUTION_RECORDS" in r.warnings


def test_no_emergency_decision_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw(emergency_decisions=[]))
    assert r.overall_status == WARNING and "EMERGENCY_DECISION_EXISTS" in r.warnings


def test_overall_readiness_pure():
    checks = [{"name": "A", "status": "PASS", "mandatory": True},
              {"name": "B", "status": "FAILED", "mandatory": True}]
    st, mf, _ = M.overall_readiness(checks)
    assert st == FAILED and mf == ["B"]
    checks2 = [{"name": "A", "status": "WARNING", "mandatory": False}]
    assert M.overall_readiness(checks2)[0] == WARNING
    checks3 = [{"name": "A", "status": "PASS", "mandatory": True}]
    assert M.overall_readiness(checks3)[0] == READY


def test_checklist_has_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().assess(T0, **_ready_kw())
    cats = {c["category"] for c in r.checks}
    assert cats == {"Health", "Incident", "Emergency", "ExecutionBoundary", "Audit"}
    assert len(r.checks) == 13


# ── 16~19. Evidence ──
def test_evidence_deterministic_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r1 = _eng().assess(T0, **_ready_kw())
    r2 = _eng().assess(T1, **_ready_kw())   # 다른 시각·동일 상태
    assert r1.evidence_hash == r2.evidence_hash
    assert r1.checklist_hash == r2.checklist_hash


def test_evidence_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.assess(T0, commit=True, **_ready_kw())
    eng.assess(T1, commit=True, **_ready_kw())   # 동일 상태 → evidence_id 동일 → 중복 방지
    assert len(ledger.read_evidence()) == 1


def test_evidence_append_only_on_state_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.assess(T0, commit=True, **_ready_kw())
    eng.assess(T1, commit=True, **_ready_kw(incidents=_warn_inc()))   # 상태 변경 → 새 증거
    assert len(ledger.read_evidence()) == 2


def test_evidence_recorded_on_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().assess(T0, commit=True, **_ready_kw())
    ev = ledger.read_evidence()
    assert len(ev) == 1 and "observed" in ev[0] and ev[0]["evidence_hash"]


# ── 20~22. Checklist ──
def test_checklist_recorded_on_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().assess(T0, commit=True, **_ready_kw())
    assert len(ledger.read_checklists()) == 1


def test_checklist_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.assess(T0, commit=True, **_ready_kw())
    eng.assess(T1, commit=True, **_ready_kw())
    assert len(ledger.read_checklists()) == 1


def test_checklist_hash_deterministic():
    checks = [{"name": "A", "status": "PASS", "mandatory": True}]
    assert M.checklist_hash(checks) == M.checklist_hash(list(checks))


# ── 23~25. Readiness ledger ──
def test_readiness_recorded_on_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().assess(T0, commit=True, **_ready_kw())
    assert len(ledger.read_readiness()) == 1


def test_readiness_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.assess(T0, commit=True, **_ready_kw())
    eng.assess(T1, commit=True, **_ready_kw())   # 동일 상태 → report_id 동일 → 중복 방지
    assert len(ledger.read_readiness()) == 1


def test_readiness_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.recovery_control.verify import verify_ledger
    eng = _eng()
    eng.assess(T0, commit=True, **_ready_kw())
    eng.assess(T1, commit=True, **_ready_kw(incidents=_warn_inc()))
    assert verify_ledger(ledger.READINESS)["ok"]


# ── 26~33. Attestation ──
def test_attest_approve_requires_checklist(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()   # no assess → no readiness
    with pytest.raises(RecoveryAttestationError):
        eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T0, commit=True)


def test_attest_approve_on_failed_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw(health={"overall_status": "CRITICAL",
                     "subsystems": []}))
    assert rep.overall_status == FAILED
    with pytest.raises(RecoveryAttestationError):
        eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T0, report=rep, commit=True)


def test_attest_reject_recorded_even_on_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw(health={"overall_status": "CRITICAL",
                     "subsystems": []}))
    att = eng.attest("op", "INC:1", REJECT, T0, reason="not ready", report=rep, commit=True)
    assert att.decision == REJECT
    assert len(ledger.read_attestations()) == 1


def test_attest_approve_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw())
    att = eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T0, report=rep, commit=True)
    assert att.decision == APPROVE_RESTART_REVIEW
    assert att.readiness_status == READY
    assert len(ledger.read_attestations()) == 1


def test_attest_duplicate_prevented(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw())
    eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T0, report=rep, commit=True)
    eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T1, report=rep, commit=True)  # 동일 → 중복 방지
    assert len(ledger.read_attestations()) == 1


def test_attest_invalid_decision_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw())
    with pytest.raises(RecoveryAttestationError):
        eng.attest("op", "INC:1", "DISABLE_KILL_SWITCH", T0, report=rep, commit=True)


def test_attest_records_hashes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw())
    att = eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T0, report=rep)
    assert att.checklist_hash == rep.checklist_hash and att.evidence_hash == rep.evidence_hash


def test_attest_does_not_touch_emergency(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw())
    eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T0, report=rep, commit=True)
    # P9.3 원장은 P9.4가 절대 쓰지 않음
    assert not os.path.exists(sp("emergency_decisions.jsonl"))
    assert not os.path.exists(sp("recovery_events.jsonl"))


# ── 34~40. Verify / tamper / duplicate / replay ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.recovery_control.verify import verify_chain
    res = verify_chain()
    assert res["ok"] and res["n"] == 0


def test_verify_chain_intact_after_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.recovery_control.verify import verify_chain
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw())
    eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T0, report=rep, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 4


def test_verify_detects_evidence_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.recovery_control.verify import verify_chain
    _eng().assess(T0, commit=True, **_ready_kw())
    path = sp("recovery_evidence.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["observed"]["kill_latch"] = True   # 관측 변조
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    res = verify_chain()
    assert not res["ok"]
    assert res["ledgers"]["recovery_evidence.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_readiness_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.recovery_control.verify import verify_chain
    _eng().assess(T0, commit=True, **_ready_kw())
    path = sp("recovery_readiness.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["overall_status"] = FAILED   # 결과 변조
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    res = verify_chain()
    assert res["ledgers"]["recovery_readiness.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.recovery_control.verify import verify_chain
    eng = _eng()
    eng.assess(T0, commit=True, **_ready_kw())
    eng.assess(T1, commit=True, **_ready_kw(incidents=_warn_inc()))
    path = sp("recovery_evidence.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = verify_chain()
    assert res["ledgers"]["recovery_evidence.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.recovery_control.verify import verify_chain
    _eng().assess(T0, commit=True, **_ready_kw())
    path = sp("recovery_evidence.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    res = verify_chain()
    assert not res["ok"]
    assert res["ledgers"]["recovery_evidence.jsonl"]["reason"] in {"duplicate_id",
                                                                   "previous_hash_broken"}


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.recovery_control.verify import replay
    res = replay(_eng(), T0, **_ready_kw(incidents=_crit_inc()))
    assert res["deterministic"] is True


# ── 41~45. CLI ──
def _iso_all(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.recovery_control.ledger.state_path", sp)


def test_cli_check(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.recovery_control.__main__ import main
    assert main(["check"]) == 0
    assert "overall_status" in capsys.readouterr().out


def test_cli_status(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.recovery_control.__main__ import main
    assert main(["status"]) == 0
    assert "attestations" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.recovery_control.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.recovery_control.__main__ import main
    assert main(["replay"]) == 0
    assert "deterministic" in capsys.readouterr().out


def test_cli_attest(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.recovery_control.__main__ import main
    rc = main(["attest", "--operator", "op", "--incident", "INC:1",
               "--decision", "REJECT", "--reason", "manual", "--commit"])
    assert rc == 0
    assert "attestation" in capsys.readouterr().out


# ── 46~58. 보안/안전 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "operations", _j + "emergency", _j + "portfolio", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.recovery_control.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.recovery_control.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", "route_order",
                       ".buy(", ".sell(", "disarm(", "restart_service", "LiveExecutionEngine"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_gateway():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.recovery_control.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "send_order",
                       "create_order", "reconnect("):
            assert banned not in src, f"{m} has broker/gateway verb {banned}"


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("recovery", "attest", "readiness", "restart", "recover"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def _mutation_guard(tmp_path, monkeypatch, filename):
    sp = _iso(tmp_path, monkeypatch)
    target = sp(filename)
    with open(target, "w") as f:
        f.write(json.dumps({"pre": "existing", "timestamp": T0}) + "\n")
    before = hashlib.sha256(open(target, "rb").read()).hexdigest()
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw(incidents=_crit_inc()))
    eng.attest("op", "INC:1", REJECT, T0, report=rep, commit=True)
    after = hashlib.sha256(open(target, "rb").read()).hexdigest()
    assert after == before, f"{filename} was mutated"


def test_no_risk_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "execution_risk_reports.jsonl")


def test_no_registry_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "registry.jsonl")


def test_no_portfolio_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "portfolio_snapshots.jsonl")


def test_no_paper_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "paper_positions.jsonl")


def test_no_emergency_mutation(tmp_path, monkeypatch):
    # 관측 입력(P9.3 비상 원장)을 읽기만 하고 절대 쓰지 않음
    _mutation_guard(tmp_path, monkeypatch, "emergency_decisions.jsonl")


def test_no_automatic_recovery_path(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    # 여러 사이클 + 승인 증언을 해도 P9.3 복구/비상 원장은 절대 생성/변경되지 않음
    rep = eng.assess(T0, commit=True, **_ready_kw())
    eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T0, report=rep, commit=True)
    for f in ("emergency_decisions.jsonl", "recovery_requests.jsonl", "recovery_events.jsonl",
              "recovery_approvals.jsonl", "live_execution_responses.jsonl"):
        assert not os.path.exists(sp(f)), f"P9.4 wrote to {f}"


def test_reads_inputs_as_data_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 계층 코드 import 없이 원장 파일만으로 KILL_ACTIVE 관측 → FAILED
    with open(sp("emergency_decisions.jsonl"), "w") as f:
        f.write(json.dumps({"emergency_state": "KILL_ACTIVE"}) + "\n")
    with open(sp("system_health_reports.jsonl"), "w") as f:
        f.write(json.dumps({"overall_status": "HEALTHY", "subsystems": []}) + "\n")
    r = _eng().assess(T0, live_enabled=False, commit=True)   # 입력 미주입 → 파일 관측
    assert r.overall_status == FAILED and "EMERGENCY_NOT_KILL_ACTIVE" in r.mandatory_failures


def test_attestation_is_not_permission(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rep = eng.assess(T0, commit=True, **_ready_kw())
    att = eng.attest("op", "INC:1", APPROVE_RESTART_REVIEW, T0, report=rep)
    keys = set(att.to_dict())
    for f in ("permission", "grant", "authorize", "enable_live", "disable_kill", "order_id"):
        assert f not in keys


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
