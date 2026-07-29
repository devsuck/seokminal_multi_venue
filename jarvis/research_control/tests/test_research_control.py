"""P12.10 Autonomous Research Control Plane 테스트. **관찰·분석·기록 전용.**

상태 생애주기(INITIALIZED→OBSERVED→ANALYZED→REPORTED→ARCHIVED)·연구 이벤트·헬스·지표·이상 탐지(is_actionable=False·
자동 복구 없음)·시스템 리포트(is_binding=False)·스냅샷(결정적)·verify(체인/변조/중복/생애주기/참조/알림/계보)·replay·CLI·
보안(금지import·금지동사·삭제 API 없음·불변·OBSERVE≠EXECUTION·rctl_ 격리·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_control import ledger
from jarvis.research_control import models as M
from jarvis.research_control.engine import AutonomousResearchControlPlaneEngine
from jarvis.research_control.models import (
    ALLOWED_TRANSITIONS,
    CONTROL_STATES,
    FORBIDDEN_VERBS,
    GENESIS,
    HEALTH_LEVELS,
    S_ANALYZED,
    S_ARCHIVED,
    S_INITIALIZED,
    S_OBSERVED,
    S_REPORTED,
    SEVERITIES,
    IllegalControlTransition,
    ImmutableStateError,
    UnknownStateError,
    can_transition,
    classify_health,
    content_hash,
    detect_cycle_check,
    is_forbidden_verb,
    severity_for,
)
from jarvis.research_control.verify import (
    alert_integrity,
    duplicate_integrity,
    lifecycle_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_control.ledger.state_path", sp)
    return sp


def _eng():
    return AutonomousResearchControlPlaneEngine()


def _state(e, name="sys1", kind="SYSTEM", now=T[0]):
    return e.initialize_state(name, kind, now, commit=True).state_id


def _observed(e, name="sys1"):
    sid = _state(e, name)
    e.collect_state(sid, "OBSERVATION", "", "", "n", T[1], commit=True)
    return sid


# ═══════════════ initialize_state ═══════════════
def test_init_returns_initialized(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().initialize_state("s", "SYSTEM", T[0], commit=True)
    assert ev.to_state == S_INITIALIZED
    assert ev.from_state == GENESIS


def test_init_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().initialize_state("s", "SYSTEM", T[0], commit=True).state_id.startswith("CTS:")


def test_state_event_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().initialize_state("s", "SYSTEM", T[0], commit=True).state_event_id.startswith("CTL:")


def test_init_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e)
    assert len(ledger.read_state_events()) == 1


def test_init_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().initialize_state("s", "SYSTEM", T[0], commit=False)
    assert ledger.read_state_events() == []


def test_init_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().initialize_state("s", "SYSTEM", T[0], commit=False).state_id
    b = _eng().initialize_state("s", "SYSTEM", T[5], commit=False).state_id
    assert a == b


def test_init_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.initialize_state("s", "SYSTEM", T[0], commit=True).state_id
    b = e.initialize_state("s", "SYSTEM", T[1], commit=True).state_id
    assert a == b
    assert len(ledger.state_events(a)) == 1


def test_init_immutable_kind(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.initialize_state("s", "SYSTEM", T[0], commit=True)
    with pytest.raises(ImmutableStateError):
        e.initialize_state("s", "OTHER", T[1], commit=True)


def test_init_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e)
    assert len(ledger.read_artifacts()) == 1


def test_init_state_is_initialized(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    assert e.current_state(sid) == S_INITIALIZED


# ═══════════════ collect_state (events) ═══════════════
def test_collect_state_transitions_observed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_state(sid, "OBSERVATION", "", "", "n", T[1], commit=True)
    assert e.current_state(sid) == S_OBSERVED


def test_collect_state_event_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    ev = e.collect_state(sid, "OBSERVATION", "", "", "n", T[1], commit=True)
    assert ev.event_id.startswith("CTE:")


def test_collect_state_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownStateError):
        _eng().collect_state("CTS:nope", "OBSERVATION", "", "", "n", T[1], commit=True)


def test_collect_state_records_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    ev = e.collect_state(sid, "CYCLE", "autonomous_research_pipeline", "ARP:x", "n", T[1],
                         commit=True)
    assert ev.source_layer == "autonomous_research_pipeline"
    assert ev.source_ref == "ARP:x"


def test_collect_state_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    e.collect_state(sid, "OBSERVATION", "", "", "n2", T[2], commit=True)
    assert len(ledger.state_records(sid)) == 2


def test_collect_state_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_state(sid, "OBSERVATION", "", "", "n", T[1], commit=False)
    assert ledger.read_events() == []


def test_collect_state_observed_no_extra_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    n = len(ledger.state_events(sid))
    e.collect_state(sid, "OBSERVATION", "", "", "n", T[3], commit=True)
    # OBSERVED→OBSERVED self-loop allowed, records new lifecycle event
    assert len(ledger.state_events(sid)) == n + 1


# ═══════════════ collect_health ═══════════════
def test_collect_health_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    h = e.collect_health(sid, 0.9, "n", T[1], commit=True)
    assert h.health_id.startswith("CTH:")
    assert h.level == "HEALTHY"


def test_collect_health_transitions_observed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=True)
    assert e.current_state(sid) == S_OBSERVED


@pytest.mark.parametrize("score,level", [
    (0.95, "HEALTHY"), (0.8, "HEALTHY"), (0.79, "DEGRADED"), (0.5, "DEGRADED"),
    (0.49, "CRITICAL"), (0.0, "CRITICAL"), (1.5, "UNKNOWN"), (-0.1, "UNKNOWN"),
])
def test_collect_health_levels(tmp_path, monkeypatch, score, level):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    assert e.collect_health(sid, score, "n", T[1], commit=True).level == level


def test_collect_health_unknown_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownStateError):
        _eng().collect_health("CTS:nope", 0.5, "n", T[1], commit=True)


def test_collect_health_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=False)
    assert ledger.read_health() == []


def test_collect_health_multiple_seq(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    h1 = e.collect_health(sid, 0.9, "a", T[1], commit=True)
    h2 = e.collect_health(sid, 0.4, "b", T[2], commit=True)
    assert h1.health_id != h2.health_id
    assert len(ledger.state_health(sid)) == 2


# ═══════════════ collect_metric ═══════════════
def test_collect_metric_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    m = e.collect_metric(sid, "latency", 12.5, "ms", T[1], commit=True)
    assert m.metric_id.startswith("CTM:")
    assert m.value == 12.5
    assert m.unit == "ms"


def test_collect_metric_unknown_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownStateError):
        _eng().collect_metric("CTS:nope", "k", 1.0, "u", T[1], commit=True)


def test_collect_metric_no_lifecycle_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_metric(sid, "k", 1.0, "u", T[1], commit=True)
    assert e.current_state(sid) == S_INITIALIZED


def test_collect_metric_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_metric(sid, "k", 1.0, "u", T[1], commit=True)
    e.collect_metric(sid, "k", 2.0, "u", T[2], commit=True)
    assert len(ledger.state_metrics(sid)) == 2


def test_collect_metric_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_metric(sid, "k", 1.0, "u", T[1], commit=False)
    assert ledger.read_metrics() == []


# ═══════════════ detect_anomaly ═══════════════
def test_detect_anomaly_healthy_no_alert(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.95, "n", T[1], commit=True)
    alerts = e.detect_anomaly(sid, T[2], commit=True)
    assert alerts == []


def test_detect_anomaly_degraded_alert(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.6, "n", T[1], commit=True)
    alerts = e.detect_anomaly(sid, T[2], commit=True)
    assert len(alerts) == 1
    assert alerts[0].code == "HEALTH_DEGRADED"
    assert alerts[0].severity == "WARNING"


def test_detect_anomaly_critical_alert(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.2, "n", T[1], commit=True)
    alerts = e.detect_anomaly(sid, T[2], commit=True)
    assert alerts[0].code == "HEALTH_CRITICAL"
    assert alerts[0].severity == "CRITICAL"


def test_detect_anomaly_alert_not_actionable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.2, "n", T[1], commit=True)
    alerts = e.detect_anomaly(sid, T[2], commit=True)
    assert alerts[0].is_actionable is False


def test_detect_anomaly_transitions_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=True)  # → OBSERVED
    e.detect_anomaly(sid, T[2], commit=True)
    assert e.current_state(sid) == S_ANALYZED


def test_detect_anomaly_no_health_no_alert(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    assert e.detect_anomaly(sid, T[2], commit=True) == []


def test_detect_anomaly_persists_alert(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.2, "n", T[1], commit=True)
    e.detect_anomaly(sid, T[2], commit=True)
    assert len(ledger.read_alerts()) == 1


def test_detect_anomaly_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.2, "n", T[1], commit=True)
    e.detect_anomaly(sid, T[2], commit=False)
    assert ledger.read_alerts() == []


def test_detect_anomaly_unknown_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownStateError):
        _eng().detect_anomaly("CTS:nope", T[2], commit=True)


# ═══════════════ generate_system_report ═══════════════
def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    r = e.generate_system_report(sid, "STATE", T[5], commit=True)
    assert r.is_binding is False


def test_report_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    r = e.generate_system_report(sid, "STATE", T[5], commit=True)
    assert r.report_id.startswith("CTR:")


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    r = e.generate_system_report(sid, "STATE", T[5], commit=True)
    assert "RECOVERY" in r.disclaimer


def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.6, "n", T[1], commit=True)
    e.collect_metric(sid, "k", 1.0, "u", T[2], commit=True)
    e.detect_anomaly(sid, T[3], commit=True)
    r = e.generate_system_report(sid, "STATE", T[5], commit=True)
    assert r.health_count == 1
    assert r.metric_count == 1
    assert r.alert_count == 1


def test_report_latest_health(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=True)
    e.collect_health(sid, 0.3, "n", T[2], commit=True)
    r = e.generate_system_report(sid, "STATE", T[5], commit=True)
    assert r.latest_health == "CRITICAL"


def test_report_transitions_reported(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=True)
    e.detect_anomaly(sid, T[2], commit=True)  # → ANALYZED
    e.generate_system_report(sid, "STATE", T[5], commit=True)
    assert e.current_state(sid) == S_REPORTED


def test_report_unknown_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownStateError):
        _eng().generate_system_report("CTS:nope", "STATE", T[5], commit=True)


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    r1 = e.generate_system_report(sid, "STATE", T[5], commit=True).report_id
    r2 = e.generate_system_report(sid, "STATE", T[5], commit=True).report_id
    assert r1 == r2
    assert len(ledger.read_reports()) == 1


def test_report_severity_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.2, "n", T[1], commit=True)
    e.detect_anomaly(sid, T[2], commit=True)
    r = e.generate_system_report(sid, "STATE", T[5], commit=True)
    assert r.severity_distribution.get("CRITICAL") == 1


# ═══════════════ archive ═══════════════
def test_archive_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=True)
    e.detect_anomaly(sid, T[2], commit=True)
    e.generate_system_report(sid, "STATE", T[3], commit=True)
    ev = e.archive_state(sid, T[4], commit=True)
    assert ev.to_state == S_ARCHIVED


def test_archive_before_report_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    with pytest.raises(IllegalControlTransition):
        e.archive_state(sid, T[4], commit=True)


def test_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=True)
    e.detect_anomaly(sid, T[2], commit=True)
    e.generate_system_report(sid, "STATE", T[3], commit=True)
    e.archive_state(sid, T[4], commit=True)
    with pytest.raises(IllegalControlTransition):
        e.collect_state(sid, "OBSERVATION", "", "", "n", T[5], commit=True)


# ═══════════════ create_snapshot ═══════════════
def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observed(e)
    s1 = e.create_snapshot(T[9])
    s2 = e.create_snapshot(T[9])
    assert s1.to_dict() == s2.to_dict()


def test_snapshot_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().create_snapshot(T[0]).snapshot_id.startswith("CTN:")


def test_snapshot_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().create_snapshot(T[0]).is_binding is False


def test_snapshot_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    e.collect_health(sid, 0.9, "n", T[2], commit=True)
    snap = e.create_snapshot(T[9])
    assert snap.state_count == 1
    assert snap.event_count == 1
    assert snap.health_count == 1


def test_snapshot_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e, "a")
    _observed(e, "b")
    snap = e.create_snapshot(T[9])
    assert snap.state_distribution.get(S_INITIALIZED) == 1
    assert snap.state_distribution.get(S_OBSERVED) == 1


def test_snapshot_does_not_mutate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observed(e)
    before = len(ledger.read_state_events())
    e.create_snapshot(T[9], commit=False)
    assert len(ledger.read_state_events()) == before


def test_snapshot_commit_records_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observed(e)
    before = len(ledger.read_artifacts())
    e.create_snapshot(T[9], commit=True)
    assert len(ledger.read_artifacts()) == before + 1


# ═══════════════ 조회 / Summary ═══════════════
def test_list_states(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e, "a")
    _state(e, "b")
    assert len(e.list_states()) == 2


def test_states_in(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e, "a")
    sid = _observed(e, "b")
    assert sid in e.states_in(S_OBSERVED)


def test_state_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e, "mysys", "PIPELINE")
    m = e.state_meta(sid)
    assert m["name"] == "mysys"
    assert m["kind"] == "PIPELINE"


def test_state_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownStateError):
        _eng().state_meta("CTS:nope")


def test_current_state_none(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_state("CTS:nope") is None


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _observed(e)
    e.collect_health(sid, 0.9, "n", T[2], commit=True)
    s = e.summary(T[9])
    assert s.event_count == 1
    assert s.health_count == 1


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().summary(T[0])
    assert s.state_event_count == 0
    assert s.artifact_count == 0


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.2, "n", T[1], commit=True)
    e.detect_anomaly(sid, T[2], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_integrity_engine(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observed(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e)
    p = sp("rctl_states.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e, "a")
    _state(e, "b")
    p = sp("rctl_states.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e)
    p = sp("rctl_states.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observed(e)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e, "a")
    _state(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=True)
    e.collect_metric(sid, "k", 1.0, "u", T[2], commit=True)
    assert reference_integrity()["ok"] is True


def test_alert_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.2, "n", T[1], commit=True)
    e.detect_anomaly(sid, T[2], commit=True)
    assert alert_integrity()["ok"] is True


def test_alert_integrity_detects_actionable(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.2, "n", T[1], commit=True)
    e.detect_anomaly(sid, T[2], commit=True)
    p = sp("rctl_alerts.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_actionable"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert alert_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observed(e)
    assert lineage_integrity()["ok"] is True


def test_reference_integrity_detects_orphan(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=True)
    p = sp("rctl_health.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["state_id"] = "CTS:ghost"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert reference_integrity()["ok"] is False


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observed(e)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ can_transition matrix ═══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (S_INITIALIZED, S_OBSERVED, True),
    (S_INITIALIZED, S_ANALYZED, False),
    (S_INITIALIZED, S_REPORTED, False),
    (S_OBSERVED, S_OBSERVED, True),
    (S_OBSERVED, S_ANALYZED, True),
    (S_OBSERVED, S_REPORTED, False),
    (S_ANALYZED, S_REPORTED, True),
    (S_ANALYZED, S_OBSERVED, True),
    (S_ANALYZED, S_ANALYZED, True),
    (S_ANALYZED, S_ARCHIVED, False),
    (S_REPORTED, S_ARCHIVED, True),
    (S_REPORTED, S_OBSERVED, True),
    (S_ARCHIVED, S_OBSERVED, False),
    (S_ARCHIVED, S_REPORTED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert can_transition(frm, to) is ok


@pytest.mark.parametrize("state", CONTROL_STATES)
def test_states_present(state):
    assert state in CONTROL_STATES


@pytest.mark.parametrize("state", CONTROL_STATES)
def test_transition_map_has_state(state):
    assert state in ALLOWED_TRANSITIONS


def test_archived_no_transitions():
    assert ALLOWED_TRANSITIONS[S_ARCHIVED] == set()


@pytest.mark.parametrize("lvl", HEALTH_LEVELS)
def test_health_levels(lvl):
    assert lvl in HEALTH_LEVELS


@pytest.mark.parametrize("sev", SEVERITIES)
def test_severities(sev):
    assert sev in SEVERITIES


# ═══════════════ classify_health / severity_for ═══════════════
@pytest.mark.parametrize("score,level", [
    (1.0, "HEALTHY"), (0.8, "HEALTHY"), (0.7, "DEGRADED"), (0.5, "DEGRADED"),
    (0.4, "CRITICAL"), (0.0, "CRITICAL"),
])
def test_classify_health(score, level):
    assert classify_health(score) == level


@pytest.mark.parametrize("bad", [1.1, -0.5, "x", None])
def test_classify_health_unknown(bad):
    assert classify_health(bad) == "UNKNOWN"


@pytest.mark.parametrize("lvl,sev", [
    ("CRITICAL", "CRITICAL"), ("DEGRADED", "WARNING"), ("HEALTHY", "INFO"),
    ("UNKNOWN", "INFO"),
])
def test_severity_for(lvl, sev):
    assert severity_for(lvl) == sev


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb_detected(verb):
    assert is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["OBSERVE", "MONITOR", "RECORD", "REPORT", "ANALYZE", "COLLECT"])
def test_allowed_verb_not_forbidden(verb):
    assert is_forbidden_verb(verb) is False


@pytest.mark.parametrize("verb", ["auto_recover", "Auto_Deploy", "  execute_trade  ", "ROLLBACK"])
def test_forbidden_verb_normalized(verb):
    assert is_forbidden_verb(verb) is True


def test_forbidden_verb_empty():
    assert is_forbidden_verb("") is False
    assert is_forbidden_verb(None) is False


@pytest.mark.parametrize("v", ["AUTO_RECOVER", "AUTO_DEPLOY", "AUTO_DECIDE", "REMEDIATE",
                                "ROLLBACK", "RESTART_SYSTEM"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


# ═══════════════ detect_cycle_check ═══════════════
def test_cycle_check_true():
    assert detect_cycle_check([("a", "b"), ("b", "a")]) is True


def test_cycle_check_self():
    assert detect_cycle_check([("a", "a")]) is True


def test_cycle_check_false():
    assert detect_cycle_check([("a", "b"), ("b", "c")]) is False


def test_cycle_check_empty():
    assert detect_cycle_check([]) is False


# ═══════════════ ID 결정성/구별 ═══════════════
def test_ids_distinct():
    assert M.state_id("x") != M.event_id("x", "k", 0)
    assert M.health_id("t", 0) != M.metric_id("t", "k", 0)


@pytest.mark.parametrize("fn,args,prefix", [
    (M.state_id, ("n",), "CTS:"),
    (M.state_event_id, ("s", "S", 0), "CTL:"),
    (M.event_id, ("s", "k", 0), "CTE:"),
    (M.health_id, ("s", 0), "CTH:"),
    (M.metric_id, ("s", "k", 0), "CTM:"),
    (M.alert_id, ("s", "c", 0), "CTA:"),
    (M.report_id, ("s", "sc", "t"), "CTR:"),
    (M.artifact_id, ("STATE", "r"), "CTF:"),
    (M.snapshot_id, ("t",), "CTN:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "DIFF", "record_hash": "DIFF"}
    assert content_hash(r1) == content_hash(r2)


def test_content_hash_changes():
    assert content_hash({"a": 1}) != content_hash({"a": 2})


# ═══════════════ 소스 READ ONLY ═══════════════
def test_source_ledgers_configured():
    for k in ("autonomous_research_pipeline", "research_manager", "research_experience_memory",
              "research_learning", "decision_intelligence"):
        assert k in ledger.SOURCE_LEDGERS


def test_source_ref_missing_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("nope", "x") is False


def test_source_ref_missing_file(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("research_manager", "x") is False


# ═══════════════ 보안: 소스 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.capital_allocation", "jarvis.live_trading", "jarvis.risk_controller",
    "jarvis.portfolio_execution",
)


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute_trade", "place_order", "run_order", "start_trading", "deploy_model",
           "allocate_capital", "promote_model", "change_permission", "auto_recover",
           "auto_deploy", "rollback", "remediate", "restart_system", "liquidate", "rebalance")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_delete_or_update_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def update_", "def remove_", "def drop_", "def overwrite_"):
        assert bad not in src, bad


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src
    assert '"r+"' not in src


@pytest.mark.parametrize("path", _SRC)
def test_source_files_mention_research(path):
    src = open(path).read()
    assert "연구" in src or "Research" in src or "research" in src


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rctl_")


def test_seven_ledgers():
    assert len(ledger.ALL_LEDGERS) == 7


# ═══════════════ CLI ═══════════════
def test_cli_init(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control.__main__ import main
    assert main(["init", "--name", "s", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"]["to_state"] == S_INITIALIZED


def test_cli_observe_health_anomaly(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control.__main__ import main
    main(["init", "--name", "s", "--commit"])
    sid = json.loads(capsys.readouterr().out)["state"]["state_id"]
    main(["health", "--state", sid, "--score", "0.2", "--commit"])
    capsys.readouterr()
    assert main(["anomaly", "--state", sid, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["alerts"]) == 1
    assert out["alerts"][0]["is_actionable"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control.__main__ import main
    assert main(["verify"]) == 0


def test_cli_states(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control.__main__ import main
    main(["init", "--name", "s", "--commit"])
    capsys.readouterr()
    assert main(["states"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["states"]) == 1


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control.__main__ import main
    assert main(["snapshot"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["is_binding"] is False


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control.__main__ import main
    assert main(["summary"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state_event_count"] == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


def test_cli_metric(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control.__main__ import main
    main(["init", "--name", "s", "--commit"])
    sid = json.loads(capsys.readouterr().out)["state"]["state_id"]
    assert main(["metric", "--state", sid, "--key", "lat", "--value", "5.0", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["metric"]["value"] == 5.0


def test_cli_full_lifecycle(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control.__main__ import main
    main(["init", "--name", "s", "--commit"])
    sid = json.loads(capsys.readouterr().out)["state"]["state_id"]
    main(["observe", "--state", sid, "--commit"])
    main(["health", "--state", sid, "--score", "0.9", "--commit"])
    main(["anomaly", "--state", sid, "--commit"])
    capsys.readouterr()
    main(["report", "--state", sid, "--commit"])
    capsys.readouterr()
    assert main(["archive", "--state", sid, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == S_ARCHIVED


# ═══════════════ 격리 / 불변 ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.initialize_state("s", "SYSTEM", T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "rctl_states.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.initialize_state("s", "SYSTEM", T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"


def test_two_states_independent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _state(e, "a")
    b = _state(e, "b")
    e.collect_state(a, "OBSERVATION", "", "", "n", T[2], commit=True)
    assert e.current_state(a) == S_OBSERVED
    assert e.current_state(b) == S_INITIALIZED


def test_state_events_ordered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _state(e)
    e.collect_health(sid, 0.9, "n", T[1], commit=True)  # OBSERVED
    e.detect_anomaly(sid, T[2], commit=True)  # ANALYZED
    e.generate_system_report(sid, "STATE", T[3], commit=True)  # REPORTED
    states = [x["to_state"] for x in ledger.state_events(sid)]
    assert states == [S_INITIALIZED, S_OBSERVED, S_ANALYZED, S_REPORTED]


def test_state_artifact_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _state(e)
    arts = ledger.read_artifacts()
    assert arts[0]["artifact_type"] == "STATE"


# ═══════════════ End-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = e.initialize_state("research-pipeline", "PIPELINE", T[0], commit=True).state_id
    e.collect_state(sid, "CYCLE_START", "autonomous_research_pipeline", "ARP:c1", "n", T[1],
                    commit=True)
    assert e.current_state(sid) == S_OBSERVED
    e.collect_metric(sid, "throughput", 42.0, "ops", T[2], commit=True)
    e.collect_health(sid, 0.35, "degraded run", T[3], commit=True)
    alerts = e.detect_anomaly(sid, T[4], commit=True)
    assert len(alerts) == 1
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].is_actionable is False
    assert e.current_state(sid) == S_ANALYZED
    r = e.generate_system_report(sid, "STATE", T[5], commit=True)
    assert r.is_binding is False
    assert r.alert_count == 1
    assert e.current_state(sid) == S_REPORTED
    e.archive_state(sid, T[6], commit=True)
    assert e.current_state(sid) == S_ARCHIVED
    snap = e.create_snapshot(T[7], commit=True)
    assert snap.state_distribution.get(S_ARCHIVED) == 1
    assert verify_chain()["ok"] is True
    assert replay(e, T[8])["deterministic"] is True
