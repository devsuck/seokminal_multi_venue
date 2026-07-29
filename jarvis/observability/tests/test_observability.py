"""P17 observability 테스트 — 건강 생애주기·지표·관찰·알림·성능·가용성·감사·대시보드·
verify·replay·데이터품질·계보·CLI·보안."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.observability import ledger
from jarvis.observability import models as M
from jarvis.observability.engine import ObservabilityEngine
from jarvis.observability.models import (
    ALERT_TYPES,
    ALLOWED_TRANSITIONS,
    FORBIDDEN_VERBS,
    GENESIS,
    HEALTH_STATES,
    H_DEGRADED,
    H_FAILED,
    H_HEALTHY,
    H_RECOVERED,
    H_UNKNOWN,
    H_WARNING,
    QUALITY_CODES,
    SEVERITIES,
    IllegalHealthTransition,
    ImmutableTargetError,
    UnknownTargetError,
    can_transition,
    classify_health,
    content_hash,
    detect_cycle_check,
    is_forbidden_verb,
)
from jarvis.observability.verify import (
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
    monkeypatch.setattr("jarvis.observability.ledger.state_path", sp)
    return sp


def _eng():
    return ObservabilityEngine()


def _target(e, name="alpha_intelligence", kind="RESEARCH_LAYER", now=T[0]):
    return e.register_target(name, kind, now, commit=True).target_id


# ═══════════════ register_target ═══════════════
def test_register_returns_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_target("t", "RESEARCH_LAYER", T[0], commit=True)
    assert ev.to_state == H_UNKNOWN
    assert ev.from_state == GENESIS


def test_register_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_target("t", now=T[0], commit=True)
    assert ev.target_id.startswith("OIU:")
    assert ev.health_event_id.startswith("OIH:")


def test_register_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e)
    assert len(ledger.read_health_events()) == 1


def test_register_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_target("t", now=T[0], commit=False)
    assert ledger.read_health_events() == []


def test_register_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_target("t", now=T[0], commit=True).target_id
    b = e.register_target("t", now=T[1], commit=True).target_id
    assert a == b
    assert len(ledger.target_events(a)) == 1


def test_register_immutable_kind(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_target("t", "RESEARCH_LAYER", T[0], commit=True)
    with pytest.raises(ImmutableTargetError):
        e.register_target("t", "OTHER", T[1], commit=True)


def test_register_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e)
    assert len(ledger.read_artifacts()) == 1


def test_register_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_target("t", now=T[0], commit=False).target_id
    b = _eng().register_target("t", now=T[5], commit=False).target_id
    assert a == b


# ═══════════════ observe_health (전이) ═══════════════
def test_health_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    ev = e.observe_health(tid, H_HEALTHY, "ok", T[1], commit=True)
    assert ev.to_state == H_HEALTHY
    assert e.current_health(tid) == H_HEALTHY


def test_health_invalid_transition_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    # UNKNOWN → RECOVERED 는 불가
    with pytest.raises(IllegalHealthTransition):
        e.observe_health(tid, H_RECOVERED, "x", T[1], commit=True)


def test_health_failed_to_healthy_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.observe_health(tid, H_FAILED, "down", T[1], commit=True)
    with pytest.raises(IllegalHealthTransition):
        e.observe_health(tid, H_HEALTHY, "x", T[2], commit=True)


def test_health_recovery_path(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.observe_health(tid, H_FAILED, "down", T[1], commit=True)
    e.observe_health(tid, H_RECOVERED, "recovering", T[2], commit=True)
    e.observe_health(tid, H_HEALTHY, "back", T[3], commit=True)
    assert e.current_health(tid) == H_HEALTHY


def test_health_unknown_target(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownTargetError):
        _eng().observe_health("OIU:nope", H_HEALTHY, "x", T[1], commit=True)


def test_health_self_loop(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.observe_health(tid, H_HEALTHY, "x", T[1], commit=True)
    e.observe_health(tid, H_HEALTHY, "still", T[2], commit=True)
    assert e.current_health(tid) == H_HEALTHY


def test_targets_in_health(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    t1 = _target(e, "a")
    _target(e, "b")
    e.observe_health(t1, H_HEALTHY, "x", T[2], commit=True)
    assert t1 in e.targets_in_health(H_HEALTHY)


# ═══════════════ can_transition matrix ═══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (H_UNKNOWN, H_HEALTHY, True), (H_UNKNOWN, H_FAILED, True), (H_UNKNOWN, H_RECOVERED, False),
    (H_HEALTHY, H_WARNING, True), (H_HEALTHY, H_RECOVERED, False),
    (H_WARNING, H_DEGRADED, True), (H_DEGRADED, H_RECOVERED, True), (H_DEGRADED, H_HEALTHY, True),
    (H_FAILED, H_RECOVERED, True), (H_FAILED, H_HEALTHY, False), (H_FAILED, H_WARNING, False),
    (H_RECOVERED, H_HEALTHY, True), (H_RECOVERED, H_FAILED, True),
])
def test_can_transition_matrix(frm, to, ok):
    assert can_transition(frm, to) is ok


@pytest.mark.parametrize("state", HEALTH_STATES)
def test_states_in_map(state):
    assert state in ALLOWED_TRANSITIONS


def test_six_states():
    assert len(HEALTH_STATES) == 6


# ═══════════════ classify_health ═══════════════
@pytest.mark.parametrize("score,state", [
    (1.0, H_HEALTHY), (0.9, H_HEALTHY), (0.8, H_WARNING), (0.7, H_WARNING),
    (0.6, H_DEGRADED), (0.4, H_DEGRADED), (0.3, H_FAILED), (0.0, H_FAILED),
    (1.5, H_UNKNOWN), (-0.1, H_UNKNOWN),
])
def test_classify_health(score, state):
    assert classify_health(score) == state


def test_classify_health_bad_type():
    assert classify_health("x") == H_UNKNOWN


# ═══════════════ metrics ═══════════════
def test_record_metric(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = e.record_metric("pipeline_exec", 5, "count", "alpha", {"env": "test"}, T[0], commit=True)
    assert m.metric_id.startswith("OIM:")
    assert m.value == 5.0
    assert m.metadata == {"env": "test"}


def test_metric_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().record_metric("k", 1, now=T[0], commit=False)
    assert ledger.read_metrics() == []


def test_metric_multiple_seq(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = e.record_metric("k", 1, now=T[0], commit=True)
    m2 = e.record_metric("k", 2, now=T[1], commit=True)
    assert m1.metric_id != m2.metric_id
    assert len(ledger.metrics_by_key("k")) == 2


def test_collect_source_metrics_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 소스 원장 시드(READ ONLY 대상)
    p = sp("ai_signals.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"signal_hash": f"s{i}"}) + "\n")
    before = open(p).read()
    e = _eng()
    metrics = e.collect_source_metrics(T[0], commit=True)
    assert any(m.key == "source_count:alpha_intelligence" and m.value == 3 for m in metrics)
    assert open(p).read() == before  # 소스 불변


def test_collect_covers_all_targets(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    metrics = e.collect_source_metrics(T[0], commit=True)
    assert len(metrics) == len(ledger.MONITOR_TARGETS)


@pytest.mark.parametrize("target", sorted(ledger.MONITOR_TARGETS))
def test_monitor_target_present(target):
    assert target in ledger.MONITOR_TARGETS


def test_monitor_targets_include_spec():
    for t in ("strategy_governance", "alpha_intelligence", "portfolio_research",
              "knowledge_graph", "agent_governance", "decision_intelligence", "simulation",
              "security"):
        assert t in ledger.MONITOR_TARGETS


# ═══════════════ observations / data quality ═══════════════
def test_record_observation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    o = e.record_observation("STALE_DATA", "feed", "12h old", {}, T[0], commit=True)
    assert o.observation_id.startswith("OIO:")
    assert o.code == "STALE_DATA"


def test_data_quality_duplicates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    recs = [{"record_hash": "a"}, {"record_hash": "a"}, {"record_hash": "b"}]
    obs = e.check_data_quality(recs, now=T[0], commit=True)
    assert any(o.code == "DUPLICATE_ARTIFACT" for o in obs)


def test_data_quality_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    recs = [{"record_hash": "a", "parent": ""}, {"record_hash": "b", "parent": "ghost"}]
    obs = e.check_data_quality(recs, parent_field="parent", now=T[0], commit=True)
    assert any(o.code == "INVALID_REFERENCE" for o in obs)


def test_data_quality_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    obs = e.check_data_quality([], now=T[0], commit=True)
    assert any(o.code == "MISSING_DATA" for o in obs)


def test_data_quality_clean(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    obs = e.check_data_quality([{"record_hash": "a"}], now=T[0], commit=True)
    assert obs == []


@pytest.mark.parametrize("code", QUALITY_CODES)
def test_quality_codes(code):
    assert code in QUALITY_CODES


# ═══════════════ performance ═══════════════
def test_record_performance(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = e.record_performance("research_cycle", 1.5, "s", {}, T[0], commit=True)
    assert p.perf_id.startswith("OIP:")
    assert p.duration == 1.5


def test_perf_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_performance("test", 1.0, now=T[0], commit=True)
    e.record_performance("test", 2.0, now=T[1], commit=True)
    assert len(ledger.read_perf()) == 2


# ═══════════════ availability ═══════════════
def test_record_availability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    a = e.record_availability(tid, True, "up", T[1], commit=True)
    assert a.availability_id.startswith("OIV:")
    assert a.available is True


def test_availability_unknown_target(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownTargetError):
        _eng().record_availability("OIU:nope", True, "", T[1], commit=True)


# ═══════════════ audit observation ═══════════════
def test_record_audit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.record_audit_observation("ledger:rmgr", "verified", {}, T[0], commit=True)
    assert a.audit_obs_id.startswith("OID:")


# ═══════════════ alerts (기록 전용) ═══════════════
def test_raise_alert(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.raise_alert("INTEGRITY_FAILURE", "CRITICAL", "rmgr_plans", "chain break", {}, T[0],
                      commit=True)
    assert a.alert_id.startswith("OIA:")
    assert a.is_actionable is False


def test_alert_not_actionable_always(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for at in ALERT_TYPES:
        a = e.raise_alert(at, "WARNING", "x", "", {}, T[0], commit=False)
        assert a.is_actionable is False


def test_alert_on_health_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.observe_health(tid, H_FAILED, "down", T[1], commit=True)
    a = e.alert_on_health(tid, T[2], commit=True)
    assert a is not None
    assert a.alert_type == "PIPELINE_FAILURE"


def test_alert_on_health_degraded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.observe_health(tid, H_DEGRADED, "slow", T[1], commit=True)
    a = e.alert_on_health(tid, T[2], commit=True)
    assert a.alert_type == "PERFORMANCE_DEGRADATION"


def test_alert_on_health_healthy_none(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.observe_health(tid, H_HEALTHY, "ok", T[1], commit=True)
    assert e.alert_on_health(tid, T[2], commit=True) is None


@pytest.mark.parametrize("at", ALERT_TYPES)
def test_alert_types(at):
    assert at in ALERT_TYPES


# ═══════════════ dashboards (비구속) ═══════════════
def test_system_overview_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e)
    d = e.system_overview(T[5])
    assert d.is_binding is False
    assert d.kind == "SYSTEM_OVERVIEW"


def test_pipeline_overview(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = _eng().pipeline_overview(T[0])
    assert d.payload["target_count"] == len(ledger.MONITOR_TARGETS)


def test_health_timeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.observe_health(tid, H_HEALTHY, "x", T[1], commit=True)
    d = e.health_timeline(tid, T[2])
    assert d.payload["states"] == [H_UNKNOWN, H_HEALTHY]


def test_failure_timeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.raise_alert("PIPELINE_FAILURE", "CRITICAL", "x", "", {}, T[0], commit=True)
    d = e.failure_timeline(T[1])
    assert d.payload["count"] == 1


def test_integrity_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_observation("INTEGRITY_FAILURE", "x", "", {}, T[0], commit=True)
    d = e.integrity_summary(T[1])
    assert d.payload["by_code"].get("INTEGRITY_FAILURE") == 1


def test_security_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.raise_alert("SECURITY_ISSUE", "CRITICAL", "secret", "", {}, T[0], commit=True)
    d = e.security_summary(T[1])
    assert d.payload["security_alert_count"] == 1


def test_performance_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_performance("cycle", 2.0, now=T[0], commit=True)
    e.record_performance("cycle", 4.0, now=T[1], commit=True)
    d = e.performance_summary(T[2])
    assert d.payload["by_name"]["cycle"]["avg"] == 3.0


def test_dashboard_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e)
    assert e.system_overview(T[5]).to_dict() == e.system_overview(T[5]).to_dict()


# ═══════════════ summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.record_metric("k", 1, now=T[1], commit=True)
    e.raise_alert("PIPELINE_FAILURE", "WARNING", "x", "", {}, T[2], commit=True)
    s = e.summary(T[9])
    assert s.metric_count == 1
    assert s.alert_count == 1
    assert s.health_event_count == 1


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().summary(T[0])
    assert s.health_event_count == 0


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.observe_health(tid, H_WARNING, "x", T[1], commit=True)
    e.record_metric("k", 1, now=T[2], commit=True)
    e.raise_alert("DATA_QUALITY_ISSUE", "WARNING", "x", "", {}, T[3], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_integrity_engine(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e)
    p = sp("obs_pipeline_health.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_metric("a", 1, now=T[0], commit=True)
    e.record_metric("b", 2, now=T[1], commit=True)
    p = sp("obs_system_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e)
    p = sp("obs_pipeline_health.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.observe_health(tid, H_HEALTHY, "x", T[1], commit=True)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e, "a")
    _target(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.record_availability(tid, True, "up", T[1], commit=True)
    assert reference_integrity()["ok"] is True


def test_reference_integrity_detects_orphan(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    tid = _target(e)
    e.record_availability(tid, True, "up", T[1], commit=True)
    p = sp("obs_availability_records.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["target_id"] = "OIU:ghost"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert reference_integrity()["ok"] is False


def test_alert_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.raise_alert("SECURITY_ISSUE", "CRITICAL", "x", "", {}, T[0], commit=True)
    assert alert_integrity()["ok"] is True


def test_alert_integrity_detects_actionable(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.raise_alert("SECURITY_ISSUE", "CRITICAL", "x", "", {}, T[0], commit=True)
    p = sp("obs_alert_events.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_actionable"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert alert_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _target(e)
    e.record_metric("k", 1, now=T[1], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["OBSERVE", "MONITOR", "MEASURE", "REPORT", "RECORD", "ANALYZE"])
def test_allowed_verb(verb):
    assert is_forbidden_verb(verb) is False


@pytest.mark.parametrize("verb", ["auto_recover", "Auto_Restart", " deploy ", "REMEDIATE",
                                   "auto_approve", "auto_decide"])
def test_forbidden_normalized(verb):
    assert is_forbidden_verb(verb) is True


def test_forbidden_empty():
    assert is_forbidden_verb("") is False
    assert is_forbidden_verb(None) is False


@pytest.mark.parametrize("v", ["AUTO_RECOVER", "AUTO_RESTART", "AUTO_DEPLOY", "AUTO_DECIDE",
                                "AUTO_APPROVE", "EXECUTE", "TRADE", "ALLOCATE_CAPITAL"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.target_id, ("n",), "OIU:"),
    (M.health_event_id, ("t", "S", 0), "OIH:"),
    (M.metric_id, ("k", "t", 0), "OIM:"),
    (M.observation_id, ("c", "s", 0), "OIO:"),
    (M.alert_id, ("t", "s", 0), "OIA:"),
    (M.perf_id, ("n", 0), "OIP:"),
    (M.availability_id, ("t", 0), "OIV:"),
    (M.audit_obs_id, ("s", 0), "OID:"),
    (M.artifact_id, ("TARGET", "r"), "OIF:"),
    (M.dashboard_id, ("k", "t"), "OIN:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


def test_cycle_check():
    assert detect_cycle_check([("a", "b"), ("b", "a")]) is True
    assert detect_cycle_check([("a", "b")]) is False


@pytest.mark.parametrize("sev", SEVERITIES)
def test_severities(sev):
    assert sev in SEVERITIES


# ═══════════════ CLI ═══════════════
def test_cli_register(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.observability.__main__ import main
    assert main(["register", "--name", "alpha", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["target"]["to_state"] == H_UNKNOWN


def test_cli_health_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.observability.__main__ import main
    main(["register", "--name", "alpha", "--commit"])
    tid = json.loads(capsys.readouterr().out)["target"]["target_id"]
    assert main(["health", "--target", tid, "--to", "HEALTHY", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == "HEALTHY"


def test_cli_alert(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.observability.__main__ import main
    assert main(["alert", "--type", "SECURITY_ISSUE", "--severity", "CRITICAL",
                 "--subject", "x", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["alert"]["is_actionable"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.observability.__main__ import main
    assert main(["verify"]) == 0


def test_cli_collect(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.observability.__main__ import main
    assert main(["collect", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["metrics"]) == len(ledger.MONITOR_TARGETS)


def test_cli_overview(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.observability.__main__ import main
    assert main(["overview"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["is_binding"] is False


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.observability.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.observability.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


def test_cli_performance(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.observability.__main__ import main
    assert main(["performance"]) == 0


# ═══════════════ 격리 / 불변 ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_target("t", now=T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "obs_pipeline_health.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_target("t", now=T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"


def test_eight_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("obs_")


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.live_execution", "jarvis.live_trading",
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
    bad = ("execute_trade", "place_order", "deploy_model", "allocate_capital", "promote_model",
           "change_permission", "auto_recover", "auto_restart", "auto_deploy", "auto_decide",
           "auto_approve", "remediate", "rollback")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_delete_update_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def update_", "def remove_", "def drop_", "def overwrite_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


def test_no_obs_stray_prefix_outside():
    # obs_ 접두사는 본 패키지에만
    src = open(os.path.join(_PKG, "ledger.py")).read()
    for own, _ in ledger.ALL_LEDGERS:
        assert own in src


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("di_candidates.jsonl")
    with open(p, "w") as f:
        for i in range(4):
            f.write(json.dumps({"event_id": f"e{i}"}) + "\n")
    e = _eng()
    tid = e.register_target("decision_intelligence", "RESEARCH_LAYER", T[0], commit=True).target_id
    e.collect_source_metrics(T[1], commit=True)
    e.observe_health(tid, H_DEGRADED, "slow", T[2], commit=True)
    alert = e.alert_on_health(tid, T[3], commit=True)
    assert alert.alert_type == "PERFORMANCE_DEGRADATION"
    assert alert.is_actionable is False
    e.record_performance("decision_cycle", 3.2, "s", {}, T[4], commit=True)
    e.record_availability(tid, True, "up", T[5], commit=True)
    obs = e.check_data_quality([{"record_hash": "x"}, {"record_hash": "x"}], now=T[6], commit=True)
    assert any(o.code == "DUPLICATE_ARTIFACT" for o in obs)
    e.observe_health(tid, H_RECOVERED, "recovering", T[7], commit=True)
    e.observe_health(tid, H_HEALTHY, "ok", T[8], commit=True)
    ov = e.system_overview(T[9])
    assert ov.is_binding is False
    assert verify_chain()["ok"] is True
    assert replay(e, T[10])["deterministic"] is True
    assert open(p).read()  # 소스 원장은 여전히 존재·불변
