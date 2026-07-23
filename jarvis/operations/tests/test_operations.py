"""P9.2 Operations Alerting & Incident Management 테스트. **관제 전용.**

alert(생성/severity/no-alert)·incident(생성/미생성/상태머신/차단전이/dedup)·escalation(지속/미달/
비CRITICAL/1회)·acknowledgement·resolution·해시체인·변조탐지·중복탐지·리플레이·CLI·결정성·
append-only·금지import없음·집행능력없음·브로커없음·주문없음·리스크/레지스트리/페이퍼 무변이.

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.operations import ledger
from jarvis.operations import models as M
from jarvis.operations.engine import OperationsEngine
from jarvis.operations.models import (
    ACKNOWLEDGED,
    CLOSED,
    CRITICAL,
    ERROR,
    GENESIS,
    INFO,
    MITIGATING,
    OPEN,
    RESOLVED,
    WARNING,
    IllegalTransition,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"
T_LATE = "2026-07-23T00:20:00Z"   # T1 로부터 19분


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.operations.ledger.state_path", sp)
    return sp


def _report(subsystems, *, overall="HEALTHY", rid="SHR:test"):
    """subsystems: [(name, status), ...]. overall 기본 HEALTHY(=system 알림 없음)."""
    return {"report_id": rid, "overall_status": overall,
            "subsystems": [{"name": n, "status": s, "detail": f"{n} detail"}
                           for n, s in subsystems]}


def _eng():
    return OperationsEngine(persist_threshold=2, escalation_minutes=15.0)


# ── 1~10. models 순수 규칙 ──
def test_severity_of_status_mapping():
    assert M.severity_of_status("WARNING") == WARNING
    assert M.severity_of_status("CRITICAL") == CRITICAL
    assert M.severity_of_status("OFFLINE") == ERROR
    assert M.severity_of_status("UNKNOWN") == INFO


def test_healthy_degraded_no_alert():
    assert M.severity_of_status("HEALTHY") is None
    assert M.severity_of_status("DEGRADED") is None


def test_severity_rank_order():
    assert (M.severity_rank(INFO) < M.severity_rank(WARNING)
            < M.severity_rank(ERROR) < M.severity_rank(CRITICAL))


def test_can_transition_allowed():
    assert M.can_transition("", OPEN)
    assert M.can_transition(OPEN, ACKNOWLEDGED)
    assert M.can_transition(ACKNOWLEDGED, MITIGATING)
    assert M.can_transition(MITIGATING, RESOLVED)
    assert M.can_transition(RESOLVED, CLOSED)


def test_can_transition_blocked():
    assert not M.can_transition(OPEN, CLOSED)
    assert not M.can_transition(OPEN, RESOLVED)
    assert not M.can_transition(CLOSED, OPEN)
    assert not M.can_transition(RESOLVED, OPEN)
    assert not M.can_transition(CLOSED, ACKNOWLEDGED)


def test_content_hash_excludes_hash_fields():
    a = {"alert_id": "X", "severity": WARNING, "previous_hash": "p1", "record_hash": "r1"}
    b = {"alert_id": "X", "severity": WARNING, "previous_hash": "p2", "record_hash": "r2"}
    assert M.content_hash(a) == M.content_hash(b)   # 두 해시필드 제외 → 동일


def test_content_hash_detects_change():
    a = {"alert_id": "X", "severity": WARNING}
    b = {"alert_id": "X", "severity": CRITICAL}
    assert M.content_hash(a) != M.content_hash(b)


def test_alert_key_time_independent():
    assert M.alert_key("A", WARNING) == M.alert_key("A", WARNING)
    assert M.alert_key("A", WARNING) != M.alert_key("A", CRITICAL)


def test_incident_id_deterministic():
    assert M.incident_id("A|CRITICAL", T0) == M.incident_id("A|CRITICAL", T0)
    assert M.incident_id("A|CRITICAL", T0).startswith("INC:")


def test_fold_incident_state():
    assert M.fold_incident_state([]) == ""
    assert M.fold_incident_state([{"to_state": OPEN}, {"to_state": ACKNOWLEDGED}]) == ACKNOWLEDGED


# ── 11~18. Alert 생성 ──
def test_derive_alert_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    alerts = _eng().derive_alerts(_report([("Market Data", "WARNING")]), T0)
    assert len(alerts) == 1 and alerts[0].severity == WARNING
    assert alerts[0].source == "Market Data"


def test_derive_alert_critical(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    alerts = _eng().derive_alerts(_report([("Execution Risk", "CRITICAL")]), T0)
    assert alerts[0].severity == CRITICAL


def test_derive_alert_offline_error(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    alerts = _eng().derive_alerts(_report([("Broker Readonly", "OFFLINE")]), T0)
    assert alerts[0].severity == ERROR


def test_derive_alert_unknown_info(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    alerts = _eng().derive_alerts(_report([("Registry", "UNKNOWN")]), T0)
    assert alerts[0].severity == INFO


def test_derive_no_alert_when_healthy(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    alerts = _eng().derive_alerts(_report([("A", "HEALTHY"), ("B", "DEGRADED")]), T0)
    assert alerts == []


def test_derive_includes_system_overall_alert(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    alerts = _eng().derive_alerts(
        _report([("A", "CRITICAL")], overall="CRITICAL"), T0)
    sources = {a.source for a in alerts}
    assert "system" in sources and "A" in sources   # 서브시스템 + overall


def test_alert_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.derive_alerts(_report([("A", "WARNING")]), T0, commit=True)
    eng.derive_alerts(_report([("A", "WARNING")]), T1, commit=True)   # 다른 시각 → 새 레코드
    assert len(ledger.read_alerts()) == 2


def test_alert_idempotent_same_input(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.derive_alerts(_report([("A", "WARNING")]), T0, commit=True)
    eng.derive_alerts(_report([("A", "WARNING")]), T0, commit=True)   # 동일 → 중복 방지
    assert len(ledger.read_alerts()) == 1


# ── 19~28. Incident 상태머신 ──
def test_incident_created_on_persist(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.process(_report([("A", "CRITICAL")]), T0, commit=True)       # count 1
    res = eng.process(_report([("A", "CRITICAL")]), T1, commit=True)  # count 2 → 생성
    assert len(res["incidents_opened"]) == 1
    assert res["incidents_opened"][0]["to_state"] == OPEN


def test_incident_not_created_below_threshold(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().process(_report([("A", "CRITICAL")]), T0, commit=True)   # count 1
    assert res["incidents_opened"] == []


def test_incident_not_created_for_info(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.process(_report([("A", "UNKNOWN")]), T0, commit=True)
    res = eng.process(_report([("A", "UNKNOWN")]), T1, commit=True)   # INFO 는 인시던트 없음
    assert res["incidents_opened"] == []
    assert ledger.read_incidents() == []


def test_incident_dedup_single_active(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.process(_report([("A", "CRITICAL")]), T0, commit=True)
    eng.process(_report([("A", "CRITICAL")]), T1, commit=True)   # 생성
    eng.process(_report([("A", "CRITICAL")]), T2, commit=True)   # 활성 존재 → 미생성
    inc_ids = {r["incident_id"] for r in ledger.read_incidents()}
    assert len(inc_ids) == 1


def test_incident_open_event_shape(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.process(_report([("A", "CRITICAL")]), T0, commit=True)
    res = eng.process(_report([("A", "CRITICAL")]), T1, commit=True)
    ev = res["incidents_opened"][0]
    assert ev["from_state"] == "" and ev["to_state"] == OPEN and ev["severity"] == CRITICAL


def _open_incident(eng, tmp_path):
    eng.process(_report([("A", "CRITICAL")]), T0, commit=True)
    res = eng.process(_report([("A", "CRITICAL")]), T1, commit=True)
    return res["incidents_opened"][0]["incident_id"]


def test_illegal_transition_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    inc = _open_incident(eng, tmp_path)
    with pytest.raises(IllegalTransition):
        eng.transition(inc, CLOSED, T2, commit=True)      # OPEN→CLOSED 차단
    with pytest.raises(IllegalTransition):
        eng.transition(inc, RESOLVED, T2, commit=True)    # OPEN→RESOLVED 차단


def test_transition_open_to_acknowledged(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    inc = _open_incident(eng, tmp_path)
    eng.transition(inc, ACKNOWLEDGED, T2, commit=True)
    assert M.fold_incident_state(ledger.incident_events(inc)) == ACKNOWLEDGED


def test_transition_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    inc = _open_incident(eng, tmp_path)
    eng.transition(inc, ACKNOWLEDGED, T2, commit=True)
    eng.transition(inc, MITIGATING, T2, commit=True)
    eng.transition(inc, RESOLVED, T2, commit=True)
    eng.transition(inc, CLOSED, T2, commit=True)
    assert M.fold_incident_state(ledger.incident_events(inc)) == CLOSED


def test_closed_is_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    inc = _open_incident(eng, tmp_path)
    eng.transition(inc, ACKNOWLEDGED, T2, commit=True)
    eng.transition(inc, MITIGATING, T2, commit=True)
    eng.transition(inc, RESOLVED, T2, commit=True)
    eng.transition(inc, CLOSED, T2, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition(inc, OPEN, T2, commit=True)


# ── 29~30. Acknowledgement ──
def test_acknowledge_creates_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    inc = _open_incident(eng, tmp_path)
    eng.acknowledge(inc, "operator1", T2, note="확인함", commit=True)
    assert M.fold_incident_state(ledger.incident_events(inc)) == ACKNOWLEDGED
    acks = ledger.read_acks()
    assert len(acks) == 1 and acks[0]["operator"] == "operator1"


def test_acknowledge_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    inc = _open_incident(eng, tmp_path)
    eng.acknowledge(inc, "op", T2, commit=True)
    eng.acknowledge(inc, "op", T2, commit=True)   # 동일 → 중복 방지(전이는 이미 ACK)
    assert len(ledger.read_acks()) == 1


# ── 31~35. Escalation(레코드만) ──
def test_escalation_on_critical_persist(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _open_incident(eng, tmp_path)                       # OPEN at T1
    res = eng.process(_report([("A", "CRITICAL")]), T_LATE, commit=True)   # 19분 > 15
    assert len(res["escalations"]) == 1
    assert res["escalations"][0]["level"] == 1


def test_no_escalation_under_window(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _open_incident(eng, tmp_path)                       # OPEN at T1
    res = eng.process(_report([("A", "CRITICAL")]), T2, commit=True)   # 1분 < 15
    assert res["escalations"] == []


def test_no_escalation_non_critical(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.process(_report([("A", "WARNING")]), T0, commit=True)
    eng.process(_report([("A", "WARNING")]), T1, commit=True)   # WARNING incident
    res = eng.process(_report([("A", "WARNING")]), T_LATE, commit=True)
    assert res["escalations"] == []                    # CRITICAL 아님 → 에스컬레이션 없음


def test_escalation_once_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _open_incident(eng, tmp_path)
    eng.process(_report([("A", "CRITICAL")]), T_LATE, commit=True)      # 에스컬레이션 1
    eng.process(_report([("A", "CRITICAL")]), "2026-07-23T00:30:00Z", commit=True)
    assert len(ledger.read_escalations()) == 1         # 재발송 없음


def test_escalation_no_channels_notified(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _open_incident(eng, tmp_path)
    res = eng.process(_report([("A", "CRITICAL")]), T_LATE, commit=True)
    assert res["escalations"][0]["channels_notified"] == []   # 실제 발송 없음(레코드만)


# ── 36~37. Resolution ──
def test_resolve_creates_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    inc = _open_incident(eng, tmp_path)
    eng.acknowledge(inc, "op", T2, commit=True)          # OPEN→ACKNOWLEDGED
    eng.resolve(inc, "op", T2, resolution="fixed", commit=True)   # →RESOLVED
    assert M.fold_incident_state(ledger.incident_events(inc)) == RESOLVED
    res = ledger.read_resolutions()
    assert len(res) == 1 and res[0]["resolution"] == "fixed"


def test_resolution_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    inc = _open_incident(eng, tmp_path)
    eng.acknowledge(inc, "op", T2, commit=True)
    eng.resolve(inc, "op", T2, commit=True)
    eng.resolve(inc, "op", T2, commit=True)   # 동일 → 중복 방지
    assert len(ledger.read_resolutions()) == 1


# ── 38~44. Verify / chain / tamper / duplicate / replay ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.operations.verify import verify_chain
    res = verify_chain()
    assert res["ok"] and res["n"] == 0


def test_verify_chain_intact_after_process(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.operations.verify import verify_chain
    eng = _eng()
    eng.process(_report([("A", "CRITICAL")]), T0, commit=True)
    eng.process(_report([("A", "CRITICAL")]), T1, commit=True)
    eng.process(_report([("A", "CRITICAL")]), T_LATE, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 3


def test_verify_detects_alert_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.operations.verify import verify_chain
    _eng().process(_report([("A", "WARNING")]), T0, commit=True)
    path = sp("alerts.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["severity"] = CRITICAL   # 콘텐츠 변조
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    res = verify_chain()
    assert not res["ok"]
    assert res["ledgers"]["alerts.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.operations.verify import verify_chain
    eng = _eng()
    eng.process(_report([("A", "WARNING")]), T0, commit=True)
    eng.process(_report([("A", "WARNING")]), T1, commit=True)
    path = sp("alerts.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = verify_chain()
    assert not res["ok"]
    assert res["ledgers"]["alerts.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.operations.verify import verify_chain
    _eng().process(_report([("A", "WARNING")]), T0, commit=True)
    path = sp("alerts.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:                       # 동일 레코드 재기록(중복 id)
        f.write(json.dumps(rec) + "\n")
    res = verify_chain()
    assert not res["ok"]
    assert res["ledgers"]["alerts.jsonl"]["reason"] in {"duplicate_id", "previous_hash_broken"}


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.operations.verify import replay
    res = replay(_eng(), _report([("A", "CRITICAL")], overall="CRITICAL"), T0)
    assert res["deterministic"] is True


def test_incident_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.operations.verify import verify_ledger
    eng = _eng()
    inc = _open_incident(eng, tmp_path)
    eng.acknowledge(inc, "op", T2, commit=True)
    eng.transition(inc, MITIGATING, T2, commit=True)
    assert verify_ledger(ledger.INCIDENTS)["ok"]


def test_deterministic_alert_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a1 = _eng().derive_alerts(_report([("A", "WARNING")]), T0)[0]
    a2 = _eng().derive_alerts(_report([("A", "WARNING")]), T0)[0]
    assert a1.record_hash == a2.record_hash and a1.alert_id == a2.alert_id


# ── 45~48. CLI ──
def _iso_all(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.operations.ledger.state_path", sp)
    monkeypatch.setattr("jarvis.system_health.ledger.state_path", sp)


def test_cli_check(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.operations.__main__ import main
    assert main(["check"]) == 0
    assert "result" in capsys.readouterr().out


def test_cli_status(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.operations.__main__ import main
    assert main(["status"]) == 0
    assert "incidents" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.operations.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso_all(tmp_path, monkeypatch)
    from jarvis.operations.__main__ import main
    assert main(["summary"]) == 0
    assert "open_incidents" in capsys.readouterr().out


# ── 49~57. 안전 조건(금지 import·집행/브로커/주문 없음·무변이) ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    # 접두사 연결로 구성 — 이 테스트 파일 자체에 금지 dotted 문자열이 그대로 나타나지 않게 한다
    # (jarvis/ 트리를 스캔하는 P8.1 가드 테스트에 오탐되지 않도록).
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operations.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operations.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", "route_order",
                       ".buy(", ".sell(", "gateway.", "arm_execution", "kill_switch(",
                       "LiveExecutionEngine"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_order_creation():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.operations.{m}"))
        for banned in ("broker.submit", "broker.place", "create_order", "new_order",
                       "OrderRequest(", "send_order"):
            assert banned not in src, f"{m} has broker/order verb {banned}"


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("operations" in a for a in ACTION_PERMISSIONS)
    assert not any("incident" in a.lower() for a in ACTION_PERMISSIONS)
    assert not any("alert" in a.lower() for a in ACTION_PERMISSIONS)
    assert not any("escalat" in a.lower() for a in ACTION_PERMISSIONS)


def _mutation_guard(tmp_path, monkeypatch, filename):
    sp = _iso(tmp_path, monkeypatch)
    target = sp(filename)
    with open(target, "w") as f:
        f.write(json.dumps({"pre": "existing", "timestamp": T0}) + "\n")
    before = hashlib.sha256(open(target, "rb").read()).hexdigest()
    eng = _eng()
    eng.process(_report([("A", "CRITICAL")], overall="CRITICAL"), T0, commit=True)
    eng.process(_report([("A", "CRITICAL")], overall="CRITICAL"), T1, commit=True)
    after = hashlib.sha256(open(target, "rb").read()).hexdigest()
    assert after == before, f"{filename} was mutated"


def test_no_risk_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "execution_risk_reports.jsonl")


def test_no_registry_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "registry.jsonl")


def test_no_paper_mutation(tmp_path, monkeypatch):
    _mutation_guard(tmp_path, monkeypatch, "paper_positions.jsonl")


def test_append_only_never_deletes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.process(_report([("A", "WARNING")]), T0, commit=True)
    n1 = len(ledger.read_alerts())
    eng.process(_report([("A", "WARNING")]), T1, commit=True)
    n2 = len(ledger.read_alerts())
    assert n2 > n1   # 오직 증가(삭제/재작성 없음)


def test_report_records_have_no_trade_fields():
    a = OperationsEngine().derive_alerts(_report([("A", "CRITICAL")]), T0)[0]
    keys = set(a.to_dict())
    for f in ("order_id", "authorized", "submit", "execute", "broker_order", "arm"):
        assert f not in keys


# ── 58. 불변식(live 폐쇄) ──
def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
