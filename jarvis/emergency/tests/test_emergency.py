"""P9.3 Kill Switch & Emergency Response 테스트. **비상 결정 전용.**

grade(NORMAL/WATCH/SAFE_MODE/KILL_PENDING/KILL_ACTIVE)·래치·reconcile·assess·recovery(자동금지·
operator 승인/반려)·해시체인·변조·중복·리플레이·CLI·결정성·append-only·금지import(operations 포함)·
집행/브로커/게이트웨이 없음·리스크/레지스트리/페이퍼/운영 무변이.

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.emergency import ledger
from jarvis.emergency import models as M
from jarvis.emergency.engine import EmergencyEngine
from jarvis.emergency.models import (
    KILL_ACTIVE,
    KILL_PENDING,
    NORMAL,
    RECOVERED,
    RECOVERY_PENDING,
    SAFE_MODE,
    WATCH,
    RecoveryNotPermitted,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"
T3 = "2026-07-23T00:03:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.emergency.ledger.state_path", sp)
    return sp


def _crit_inc():
    return [{"incident_id": "INC:1", "to_state": "OPEN", "severity": "CRITICAL"}]


def _warn_inc():
    return [{"incident_id": "INC:2", "to_state": "OPEN", "severity": "WARNING"}]


def _health(status):
    return {"report_id": "SHR:x", "overall_status": status, "warnings": []}


def _risk(status, warns=0):
    return {"report_id": "RSK:x", "overall_status": status,
            "warnings": [f"w{i}" for i in range(warns)]}


# ── 1~14. grade / reconcile 순수 규칙 ──
def test_grade_normal():
    st, _ = M.grade("HEALTHY", "ALLOW", 0, False, False, False)
    assert st == NORMAL


def test_grade_watch_health_warning():
    st, _ = M.grade("WARNING", "ALLOW", 0, False, False, False)
    assert st == WATCH


def test_grade_watch_health_degraded():
    st, _ = M.grade("DEGRADED", "ALLOW", 0, False, False, False)
    assert st == WATCH


def test_grade_watch_risk_warning():
    st, _ = M.grade("HEALTHY", "ALLOW", 2, False, False, False)
    assert st == WATCH


def test_grade_safe_mode_single_severe_risk_block():
    st, _ = M.grade("HEALTHY", "BLOCK", 0, False, False, False)
    assert st == SAFE_MODE


def test_grade_safe_mode_offline():
    st, _ = M.grade("OFFLINE", "ALLOW", 0, False, False, False)
    assert st == SAFE_MODE


def test_grade_safe_mode_warning_accumulation():
    st, r = M.grade("WARNING", "ALLOW", 1, False, False, False)
    assert st == SAFE_MODE and "warning_accumulation" in r


def test_grade_safe_mode_warning_incident():
    st, _ = M.grade("HEALTHY", "ALLOW", 0, False, True, False)
    assert st == SAFE_MODE


def test_grade_kill_pending_two_severe():
    st, _ = M.grade("CRITICAL", "BLOCK", 0, False, False, False)   # 2 심각신호
    assert st == KILL_PENDING


def test_grade_kill_pending_escalation():
    st, r = M.grade("HEALTHY", "ALLOW", 0, False, False, True)
    assert st == KILL_PENDING and "escalation_active" in r


def test_grade_kill_active_all_three():
    st, r = M.grade("CRITICAL", "BLOCK", 0, True, False, False)
    assert st == KILL_ACTIVE
    assert set(r) == {"health_critical", "risk_block", "critical_incident"}


def test_reconcile_latch_kill_active():
    assert M.reconcile(KILL_ACTIVE, NORMAL) == KILL_ACTIVE   # 자동 하향 금지


def test_reconcile_recovery_pending_holds():
    assert M.reconcile(RECOVERY_PENDING, NORMAL) == RECOVERY_PENDING


def test_reconcile_recovered_resumes():
    assert M.reconcile(RECOVERED, NORMAL) == NORMAL
    assert M.reconcile(NORMAL, WATCH) == WATCH   # 비래치는 판정 추종


# ── 15~23. assess ──
def test_assess_normal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = EmergencyEngine().assess(health=_health("HEALTHY"), risk=_risk("ALLOW"),
                                 incidents=[], escalations=[], now=T0)
    assert d.emergency_state == NORMAL


def test_assess_watch(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = EmergencyEngine().assess(health=_health("WARNING"), risk=_risk("ALLOW"),
                                 incidents=[], escalations=[], now=T0)
    assert d.emergency_state == WATCH


def test_assess_safe_mode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = EmergencyEngine().assess(health=_health("HEALTHY"), risk=_risk("BLOCK"),
                                 incidents=[], escalations=[], now=T0)
    assert d.emergency_state == SAFE_MODE


def test_assess_kill_pending(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = EmergencyEngine().assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
                                 incidents=[], escalations=[], now=T0)
    assert d.emergency_state == KILL_PENDING


def test_assess_kill_active(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = EmergencyEngine().assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
                                 incidents=_crit_inc(), escalations=[], now=T0)
    assert d.emergency_state == KILL_ACTIVE
    assert "risk_block" in d.reasons


def test_assess_kill_active_latches(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    eng.assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
               incidents=_crit_inc(), escalations=[], now=T0, commit=True)
    # 이후 입력이 완전 정상이어도 KILL_ACTIVE 래치 유지(자동복구 금지)
    d = eng.assess(health=_health("HEALTHY"), risk=_risk("ALLOW"),
                   incidents=[], escalations=[], now=T1, commit=True)
    assert d.emergency_state == KILL_ACTIVE
    assert eng.current_state() == KILL_ACTIVE


def test_assess_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    EmergencyEngine().assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
                             incidents=_crit_inc(), now=T0, commit=True)
    assert len(ledger.read_decisions()) == 1


def test_assess_idempotent_same_input(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    eng.assess(health=_health("HEALTHY"), risk=_risk("ALLOW"), incidents=[], now=T0, commit=True)
    eng.assess(health=_health("HEALTHY"), risk=_risk("ALLOW"), incidents=[], now=T0, commit=True)
    assert len(ledger.read_decisions()) == 1   # 동일 입력+시각 → 중복 방지


def test_current_state_reflects_last(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    assert eng.current_state() == NORMAL
    eng.assess(health=_health("HEALTHY"), risk=_risk("BLOCK"), incidents=[], now=T0, commit=True)
    assert eng.current_state() == SAFE_MODE


# ── 24~33. Recovery(자동 금지·operator 전용) ──
def _to_kill(eng):
    eng.assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
               incidents=_crit_inc(), escalations=[], now=T0, commit=True)


def test_request_recovery_requires_kill_active(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()   # NORMAL
    with pytest.raises(RecoveryNotPermitted):
        eng.request_recovery("op", T1, commit=True)


def test_request_recovery_transitions_to_pending(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    _to_kill(eng)
    eng.request_recovery("op", T1, reason="fixed root cause", commit=True)
    assert eng.current_state() == RECOVERY_PENDING
    assert len(ledger.read_recovery_requests()) == 1


def test_approve_recovery_requires_pending(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    _to_kill(eng)   # KILL_ACTIVE, not pending
    with pytest.raises(RecoveryNotPermitted):
        eng.approve_recovery("RCVQ:x", "boss", T2, approved=True, commit=True)


def test_approve_recovery_approved_to_recovered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    _to_kill(eng)
    req = eng.request_recovery("op", T1, commit=True)
    eng.approve_recovery(req["request_id"], "boss", T2, approved=True, commit=True)
    assert eng.current_state() == RECOVERED


def test_approve_recovery_rejected_relatches(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    _to_kill(eng)
    req = eng.request_recovery("op", T1, commit=True)
    eng.approve_recovery(req["request_id"], "boss", T2, approved=False, commit=True)
    assert eng.current_state() == KILL_ACTIVE   # 반려 → 재래치
    evs = ledger.read_recovery_events()
    assert evs[-1]["outcome"] == "rejected"


def test_recovery_full_flow_then_resume(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    _to_kill(eng)
    req = eng.request_recovery("op", T1, commit=True)
    eng.approve_recovery(req["request_id"], "boss", T2, approved=True, commit=True)
    # 복구 완료 후 정상 입력 → 판정 재개(NORMAL)
    d = eng.assess(health=_health("HEALTHY"), risk=_risk("ALLOW"),
                   incidents=[], escalations=[], now=T3, commit=True)
    assert d.emergency_state == NORMAL


def test_recovery_records_all_ledgers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    _to_kill(eng)
    req = eng.request_recovery("op", T1, commit=True)
    eng.approve_recovery(req["request_id"], "boss", T2, approved=True, commit=True)
    assert len(ledger.read_recovery_requests()) == 1
    assert len(ledger.read_recovery_approvals()) == 1
    assert len(ledger.read_recovery_events()) == 1


def test_no_auto_recovery(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    _to_kill(eng)
    # 여러 번 정상 관측을 반복해도 절대 스스로 복구되지 않음
    for i, t in enumerate(("2026-07-23T01:00:00Z", "2026-07-23T02:00:00Z")):
        eng.assess(health=_health("HEALTHY"), risk=_risk("ALLOW"),
                   incidents=[], escalations=[], now=t, commit=True)
    assert eng.current_state() == KILL_ACTIVE
    assert ledger.read_recovery_events() == []


def test_recovery_request_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    _to_kill(eng)
    eng.request_recovery("op", T1, commit=True)
    # 이미 RECOVERY_PENDING → 재요청은 KILL_ACTIVE 아님 → 차단
    with pytest.raises(RecoveryNotPermitted):
        eng.request_recovery("op", T1, commit=True)


def test_recovery_event_transition_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    _to_kill(eng)
    req = eng.request_recovery("op", T1, commit=True)
    eng.approve_recovery(req["request_id"], "boss", T2, approved=True, commit=True)
    ev = ledger.read_recovery_events()[-1]
    assert ev["from_state"] == RECOVERY_PENDING and ev["to_state"] == RECOVERED


# ── 34~41. Verify / tamper / duplicate / replay / hash ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.emergency.verify import verify_chain
    res = verify_chain()
    assert res["ok"] and res["n"] == 0


def test_verify_chain_intact_after_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.emergency.verify import verify_chain
    eng = EmergencyEngine()
    _to_kill(eng)
    req = eng.request_recovery("op", T1, commit=True)
    eng.approve_recovery(req["request_id"], "boss", T2, approved=True, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 4


def test_verify_detects_decision_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.emergency.verify import verify_chain
    EmergencyEngine().assess(health=_health("HEALTHY"), risk=_risk("BLOCK"),
                             incidents=[], now=T0, commit=True)
    path = sp("emergency_decisions.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["emergency_state"] = KILL_ACTIVE   # 상태 변조
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    res = verify_chain()
    assert not res["ok"]
    assert res["ledgers"]["emergency_decisions.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.emergency.verify import verify_chain
    eng = EmergencyEngine()
    eng.assess(health=_health("HEALTHY"), risk=_risk("BLOCK"), incidents=[], now=T0, commit=True)
    eng.assess(health=_health("CRITICAL"), risk=_risk("BLOCK"), incidents=[], now=T1, commit=True)
    path = sp("emergency_decisions.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = verify_chain()
    assert res["ledgers"]["emergency_decisions.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.emergency.verify import verify_chain
    EmergencyEngine().assess(health=_health("HEALTHY"), risk=_risk("BLOCK"),
                             incidents=[], now=T0, commit=True)
    path = sp("emergency_decisions.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    res = verify_chain()
    assert not res["ok"]
    assert res["ledgers"]["emergency_decisions.jsonl"]["reason"] in {"duplicate_id",
                                                                     "previous_hash_broken"}


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.emergency.verify import replay
    res = replay(EmergencyEngine(), health=_health("CRITICAL"), risk=_risk("BLOCK"),
                 incidents=_crit_inc(), escalations=[], now=T0)
    assert res["deterministic"] is True


def test_recovery_event_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.emergency.verify import verify_ledger
    eng = EmergencyEngine()
    _to_kill(eng)
    req = eng.request_recovery("op", T1, commit=True)
    eng.approve_recovery(req["request_id"], "boss", T2, approved=True, commit=True)
    assert verify_ledger(ledger.RECOVERY_EVENTS)["ok"]


def test_deterministic_decision_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d1 = EmergencyEngine().assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
                                  incidents=_crit_inc(), now=T0)
    _iso(tmp_path, monkeypatch)   # 재격리(빈 상태) → 동일 cur=NORMAL
    d2 = EmergencyEngine().assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
                                  incidents=_crit_inc(), now=T0)
    assert d1.record_hash == d2.record_hash and d1.decision_id == d2.decision_id


# ── 42~45. CLI ──
def _iso_all(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.emergency.ledger.state_path", sp)


def test_cli_check(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.emergency.__main__ import main
    assert main(["check"]) == 0
    assert "emergency_state" in capsys.readouterr().out


def test_cli_status(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.emergency.__main__ import main
    assert main(["status"]) == 0
    assert "current_state" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.emergency.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.emergency.__main__ import main
    assert main(["summary"]) == 0
    assert "state_distribution" in capsys.readouterr().out


# ── 46~57. 안전 조건 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "operations", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.emergency.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.emergency.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", "route_order",
                       ".buy(", ".sell(", "arm_execution", "disarm(", "LiveExecutionEngine"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_gateway():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.emergency.{m}"))
        for banned in ("gateway.", "broker.submit", "broker.place", "broker_api",
                       "send_order", "create_order"):
            assert banned not in src, f"{m} has broker/gateway verb {banned}"


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("emergency", "kill", "recovery", "safe_mode"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def _mutation_guard(tmp_path, monkeypatch, filename):
    sp = _iso(tmp_path, monkeypatch)
    target = sp(filename)
    with open(target, "w") as f:
        f.write(json.dumps({"pre": "existing", "timestamp": T0}) + "\n")
    before = hashlib.sha256(open(target, "rb").read()).hexdigest()
    eng = EmergencyEngine()
    eng.assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
               incidents=_crit_inc(), now=T0, commit=True)
    eng.assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
               incidents=_crit_inc(), now=T1, commit=True)
    after = hashlib.sha256(open(target, "rb").read()).hexdigest()
    assert after == before, f"{filename} was mutated"


def test_no_risk_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "execution_risk_reports.jsonl")


def test_no_registry_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "registry.jsonl")


def test_no_paper_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "paper_positions.jsonl")


def test_no_operations_mutation(tmp_path, monkeypatch):
    # 관측 대상(P9.2 인시던트 원장)을 읽기만 하고 절대 쓰지 않음
    _mutation_guard(tmp_path, monkeypatch, "incidents.jsonl")


def test_reads_inputs_as_data_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 다른 계층 코드 import 없이 원장 파일만으로 KILL_ACTIVE 도출
    with open(sp("system_health_reports.jsonl"), "w") as f:
        f.write(json.dumps(_health("CRITICAL")) + "\n")
    with open(sp("execution_risk_reports.jsonl"), "w") as f:
        f.write(json.dumps(_risk("BLOCK")) + "\n")
    with open(sp("incidents.jsonl"), "w") as f:
        f.write(json.dumps(_crit_inc()[0]) + "\n")
    d = EmergencyEngine().assess(now=T0, commit=True)   # 입력 미주입 → 파일에서 관측
    assert d.emergency_state == KILL_ACTIVE


def test_append_only_never_deletes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = EmergencyEngine()
    eng.assess(health=_health("HEALTHY"), risk=_risk("BLOCK"), incidents=[], now=T0, commit=True)
    n1 = len(ledger.read_decisions())
    eng.assess(health=_health("CRITICAL"), risk=_risk("BLOCK"), incidents=[], now=T1, commit=True)
    assert len(ledger.read_decisions()) > n1


def test_decision_has_no_trade_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = EmergencyEngine().assess(health=_health("CRITICAL"), risk=_risk("BLOCK"),
                                 incidents=_crit_inc(), now=T0)
    keys = set(d.to_dict())
    for f in ("order_id", "authorized", "submit", "execute", "broker_order",
              "cancel", "arm"):
        assert f not in keys


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
