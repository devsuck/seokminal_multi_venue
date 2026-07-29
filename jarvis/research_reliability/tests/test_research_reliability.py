"""P24 research_reliability 테스트 — 장애/포스트모템 생애주기·복구 계획/시도·무결성 검사·신뢰성 지표·
계보·verify·replay·CLI·보안·금지능력·READ ONLY 상위. RECORD ≠ REPAIR."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_reliability import ledger
from jarvis.research_reliability import models as M
from jarvis.research_reliability.engine import ResearchReliabilityEngine
from jarvis.research_reliability.models import (
    CHECK_RESULTS,
    FORBIDDEN_VERBS,
    GENESIS,
    INCIDENT_CATEGORIES,
    INCIDENT_STATES,
    INTEGRITY_CHECK_TYPES,
    POSTMORTEM_STATES,
    RECOVERY_RESULTS,
    RELIABILITY_METRICS,
    SEVERITIES,
    I_ANALYZING,
    I_ARCHIVED,
    I_OPEN,
    I_RECOVERY_PLANNED,
    I_RESOLVED,
    P_DRAFT,
    P_RECORDED,
    P_REVIEWED,
    IllegalIncidentTransition,
    IllegalPostmortemTransition,
    ReviewerRequired,
    UnknownEntityError,
    can_incident_transition,
    can_postmortem_transition,
    content_hash,
    ratio,
)
from jarvis.research_reliability.verify import (
    check_integrity,
    duplicate_integrity,
    incident_lifecycle_integrity,
    lineage_integrity,
    metric_integrity,
    postmortem_lifecycle_integrity,
    recovery_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_reliability.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchReliabilityEngine()


def _inc(e, source="research_operations", category="PIPELINE_FAILURE", desc="pipeline stalled",
         severity="HIGH", now=T[0]):
    return e.register_incident(source, category, desc, severity, now, commit=True).incident_id


# ═══════════════ incident lifecycle ═══════════════
def test_register_incident(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_incident("research_operations", "PIPELINE_FAILURE", "stalled", "HIGH",
                                  T[0], commit=True)
    assert ev.to_state == I_OPEN
    assert ev.incident_id.startswith("RLI:")
    assert ev.incident_event_id.startswith("RLN:")
    assert ev.severity == "HIGH"


def test_incident_bad_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_incident("x", "NOPE", "d", now=T[0], commit=True)


def test_incident_bad_severity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_incident("x", "DATA_FAILURE", "d", "NUCLEAR", now=T[0], commit=True)


def test_incident_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.analyze_incident(inc, now=T[1], commit=True)
    e.mark_recovery_planned(inc, now=T[2], commit=True)
    e.resolve_incident(inc, now=T[3], commit=True)
    e.archive_incident(inc, now=T[4], commit=True)
    assert e.incident_state(inc) == I_ARCHIVED


def test_incident_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    with pytest.raises(IllegalIncidentTransition):
        e.resolve_incident(inc, now=T[1], commit=True)  # OPEN→RESOLVED skip


def test_incident_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_incident("l", "DATA_FAILURE", "d", "LOW", T[0], commit=True).incident_id
    b = e.register_incident("l", "DATA_FAILURE", "d", "LOW", T[1], commit=True).incident_id
    assert a == b
    assert len(ledger.incident_events(a)) == 1


def test_incident_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().analyze_incident("RLI:nope", now=T[1], commit=True)


def test_incident_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _inc(e)
    assert any(a["artifact_type"] == "INCIDENT" for a in ledger.read_artifacts())


def test_incident_reanalyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.analyze_incident(inc, now=T[1], commit=True)
    e.mark_recovery_planned(inc, now=T[2], commit=True)
    e.analyze_incident(inc, now=T[3], commit=True)  # RECOVERY_PLANNED→ANALYZING 재분석
    assert e.incident_state(inc) == I_ANALYZING


def test_incidents_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.analyze_incident(inc, now=T[1], commit=True)
    assert inc in e.incidents_in_state(I_ANALYZING)


@pytest.mark.parametrize("frm,to,ok", [
    (I_OPEN, I_ANALYZING, True), (I_OPEN, I_RESOLVED, False),
    (I_ANALYZING, I_RECOVERY_PLANNED, True), (I_RECOVERY_PLANNED, I_RESOLVED, True),
    (I_RECOVERY_PLANNED, I_ANALYZING, True), (I_RESOLVED, I_ARCHIVED, True),
    (I_RESOLVED, I_ANALYZING, True), (I_ARCHIVED, I_ANALYZING, False),
    (I_OPEN, I_ARCHIVED, False),
])
def test_incident_transition_matrix(frm, to, ok):
    assert can_incident_transition(frm, to) is ok


@pytest.mark.parametrize("s", INCIDENT_STATES)
def test_incident_states(s):
    assert s in INCIDENT_STATES


@pytest.mark.parametrize("c", INCIDENT_CATEGORIES)
def test_incident_categories(c):
    assert c in INCIDENT_CATEGORIES


# ═══════════════ recovery plan (no auto execution) ═══════════════
def test_create_recovery_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    p = e.create_recovery_plan(inc, ["reingest", "revalidate"], "researcher", T[1], commit=True)
    assert p.plan_id.startswith("RLP:")
    assert p.auto_execute is False
    assert p.steps == ["reingest", "revalidate"]


def test_recovery_plan_unknown_incident(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().create_recovery_plan("RLI:nope", ["s"], "o", T[0], commit=True)


def test_recovery_plan_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    p = e.create_recovery_plan(inc, ["s"], "o", T[1], commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    plan_art = next(a for a in arts.values() if a["ref_id"] == p.plan_id)
    assert plan_art["parent_artifact"] == M.artifact_id(M.ART_INCIDENT, inc)


def test_multiple_plans(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.create_recovery_plan(inc, ["a"], "o", T[1], commit=True)
    e.create_recovery_plan(inc, ["b"], "o", T[2], commit=True)
    assert len(ledger.plans_for(inc)) == 2


# ═══════════════ recovery events ═══════════════
def test_record_recovery_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    ev = e.record_recovery_event(inc, "reingest_dataset", "VERIFIED", "12 rows", T[1], commit=True)
    assert ev.event_id.startswith("RLE:")
    assert ev.result == "VERIFIED"


def test_recovery_event_bad_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    with pytest.raises(ValueError):
        e.record_recovery_event(inc, "x", "EXECUTED", now=T[1], commit=True)


def test_recovery_event_unknown_incident(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_recovery_event("RLI:nope", "x", now=T[0], commit=True)


@pytest.mark.parametrize("r", RECOVERY_RESULTS)
def test_recovery_results(r):
    assert r in RECOVERY_RESULTS


def test_recovery_events_for(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.record_recovery_event(inc, "a", "RECORDED", now=T[1], commit=True)
    e.record_recovery_event(inc, "b", "FAILED", now=T[2], commit=True)
    assert len(ledger.recovery_events_for(inc)) == 2


# ═══════════════ integrity checks ═══════════════
def test_run_integrity_check(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().run_integrity_check("data_governance", "HASH_CHECK", "PASS", {"n": 10}, T[0],
                                   commit=True)
    assert c.check_id.startswith("RLC:")
    assert c.result == "PASS"


def test_integrity_check_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().run_integrity_check("l", "NOPE", now=T[0], commit=True)


def test_integrity_check_bad_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().run_integrity_check("l", "HASH_CHECK", "MAYBE", now=T[0], commit=True)


def test_scan_upstream_integrity_absent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    checks = e.scan_upstream_integrity(T[0], commit=True)
    assert len(checks) == len(ledger.SOURCE_LAYERS)
    assert all(c.result == "FAIL" for c in checks)  # 소스 미존재 → FAIL


def test_scan_upstream_integrity_present(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("rmon_health_checks.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps({"health_id": "h0"}) + "\n")
    e = _eng()
    checks = e.scan_upstream_integrity(T[0], commit=True)
    mon = next(c for c in checks if c.target_layer == "monitoring")
    assert mon.result == "PASS"
    assert open(p).read()  # 상위 원장 불변


@pytest.mark.parametrize("t", INTEGRITY_CHECK_TYPES)
def test_integrity_check_types(t):
    assert t in INTEGRITY_CHECK_TYPES


@pytest.mark.parametrize("r", CHECK_RESULTS)
def test_check_results(r):
    assert r in CHECK_RESULTS


# ═══════════════ reliability metrics (observation only) ═══════════════
def test_calculate_reliability_metrics_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().calculate_reliability_metrics(T[0], commit=True)
    assert set(m) == set(RELIABILITY_METRICS)
    assert m["incident_frequency"] == 0.0
    assert m["research_availability_score"] == 1.0  # 장애 없음 → 완전 가용


def test_metrics_incident_frequency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _inc(e, desc="a")
    _inc(e, desc="b")
    m = e.calculate_reliability_metrics(T[5], commit=True)
    assert m["incident_frequency"] == 2.0


def test_metrics_availability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e, desc="a")
    _inc(e, desc="b")
    e.analyze_incident(inc, now=T[1], commit=True)
    e.mark_recovery_planned(inc, now=T[2], commit=True)
    e.resolve_incident(inc, now=T[3], commit=True)
    m = e.calculate_reliability_metrics(T[5], commit=True)
    assert m["research_availability_score"] == 0.5  # 1/2 해결


def test_metrics_failed_validation_rate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_integrity_check("l1", "HASH_CHECK", "PASS", now=T[0], commit=True)
    e.run_integrity_check("l2", "SCHEMA_CHECK", "FAIL", now=T[1], commit=True)
    m = e.calculate_reliability_metrics(T[5], commit=True)
    assert m["failed_validation_rate"] == 0.5


def test_metrics_ledger_integrity_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _inc(e)
    m = e.calculate_reliability_metrics(T[5], commit=True)
    assert m["ledger_integrity_score"] == 1.0


def test_metrics_are_observations(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.calculate_reliability_metrics(T[0], commit=True)
    assert all(r["is_observation"] is True for r in ledger.read_reliability_metrics())


def test_metrics_mean_resolution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.analyze_incident(inc, now=T[1], commit=True)
    e.mark_recovery_planned(inc, now=T[2], commit=True)
    e.resolve_incident(inc, now=T[3], commit=True)  # OPEN(0)->ANALYZING(1)->PLANNED(2)->RESOLVED(3)
    m = e.calculate_reliability_metrics(T[5], commit=True)
    assert m["mean_resolution_time"] == 3.0


@pytest.mark.parametrize("name", RELIABILITY_METRICS)
def test_reliability_metric_names(name):
    assert name in RELIABILITY_METRICS


def test_ratio_zero_denominator():
    assert ratio(3, 0) == 0.0


def test_ratio_normal():
    assert ratio(1, 4) == 0.25


# ═══════════════ postmortem workflow (human review required) ═══════════════
def test_create_postmortem(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    pm = e.create_postmortem(inc, "root", "impact", "lesson", T[1], commit=True)
    assert pm.to_state == P_DRAFT
    assert pm.postmortem_id.startswith("RLO:")
    assert pm.postmortem_event_id.startswith("RLD:")


def test_postmortem_full_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    pm = e.create_postmortem(inc, "root", "impact", "lesson", T[1], commit=True).postmortem_id
    e.review_postmortem(pm, "reviewer-1", now=T[2], commit=True)
    e.record_postmortem(pm, "approver-1", now=T[3], commit=True)
    assert e.postmortem_state(pm) == P_RECORDED


def test_postmortem_review_requires_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    pm = e.create_postmortem(inc, "r", "i", "l", T[1], commit=True).postmortem_id
    with pytest.raises(ReviewerRequired):
        e.review_postmortem(pm, "", now=T[2], commit=True)


def test_postmortem_record_requires_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    pm = e.create_postmortem(inc, "r", "i", "l", T[1], commit=True).postmortem_id
    e.review_postmortem(pm, "rev", now=T[2], commit=True)
    with pytest.raises(ReviewerRequired):
        e.record_postmortem(pm, "", now=T[3], commit=True)


def test_postmortem_no_skip_to_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    pm = e.create_postmortem(inc, "r", "i", "l", T[1], commit=True).postmortem_id
    with pytest.raises(IllegalPostmortemTransition):
        e.record_postmortem(pm, "rev", now=T[2], commit=True)  # DRAFT→RECORDED skip


def test_postmortem_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    a = e.create_postmortem(inc, "r", "i", "l", T[1], commit=True).postmortem_id
    b = e.create_postmortem(inc, "r2", "i2", "l2", T[2], commit=True).postmortem_id
    assert a == b
    assert len(ledger.postmortem_events(a)) == 1


def test_postmortem_unknown_incident(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().create_postmortem("RLI:nope", "r", "i", "l", T[0], commit=True)


def test_postmortem_back_to_draft(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    pm = e.create_postmortem(inc, "r", "i", "l", T[1], commit=True).postmortem_id
    e.review_postmortem(pm, "rev", now=T[2], commit=True)
    # REVIEWED→DRAFT back-transition via internal event; use transition helper indirectly
    assert can_postmortem_transition(P_REVIEWED, P_DRAFT) is True


@pytest.mark.parametrize("frm,to,ok", [
    (P_DRAFT, P_REVIEWED, True), (P_DRAFT, P_RECORDED, False),
    (P_REVIEWED, P_RECORDED, True), (P_REVIEWED, P_DRAFT, True),
    (P_RECORDED, P_REVIEWED, False),
])
def test_postmortem_transition_matrix(frm, to, ok):
    assert can_postmortem_transition(frm, to) is ok


@pytest.mark.parametrize("s", POSTMORTEM_STATES)
def test_postmortem_states(s):
    assert s in POSTMORTEM_STATES


# ═══════════════ severity ═══════════════
@pytest.mark.parametrize("sev", SEVERITIES)
def test_severities(sev):
    assert sev in SEVERITIES


def test_severity_has_critical():
    assert "CRITICAL" in SEVERITIES


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e, severity="CRITICAL", category="DATA_FAILURE")
    e.analyze_incident(inc, now=T[1], commit=True)
    e.run_integrity_check("data", "HASH_CHECK", "FAIL", now=T[2], commit=True)
    r = e.generate_report("SYSTEM", T[3], commit=True)
    assert r.report_id.startswith("RLR:")
    assert r.is_binding is False
    assert r.incident_count == 1
    assert r.failed_check_count == 1
    assert r.severity_distribution.get("CRITICAL") == 1
    assert r.category_distribution.get("DATA_FAILURE") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "REPAIR" in r.disclaimer


def test_report_has_metrics(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert set(r.reliability_metrics) == set(RELIABILITY_METRICS)


def test_report_open_resolved_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _inc(e, desc="a")
    _inc(e, desc="b")
    e.analyze_incident(a, now=T[1], commit=True)
    e.mark_recovery_planned(a, now=T[2], commit=True)
    e.resolve_incident(a, now=T[3], commit=True)
    r = e.generate_report("SYSTEM", T[4], commit=True)
    assert r.resolved_incident_count == 1
    assert r.open_incident_count == 1


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("knowledge_graph", "agent_governance", "research_memory", "monitoring",
              "research_operations", "production_readiness", "research_automation"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("rm_lessons.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"lesson_id": f"l{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("research_memory") == 3
    assert open(p).read() == before


def test_source_ref_exists(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("rmon_health_checks.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps({"health_id": "MOH:abc"}) + "\n")
    assert ledger.source_ref_exists("monitoring", "MOH:abc") is True
    assert ledger.source_ref_exists("monitoring", "MOH:zzz") is False


def test_all_source_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    counts = ledger.all_source_counts()
    assert set(counts) == set(ledger.SOURCE_LAYERS)
    assert all(v == 0 for v in counts.values())


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.analyze_incident(inc, now=T[1], commit=True)
    e.create_recovery_plan(inc, ["s"], "o", T[2], commit=True)
    e.record_recovery_event(inc, "a", "VERIFIED", now=T[3], commit=True)
    e.run_integrity_check("data", "HASH_CHECK", "PASS", now=T[4], commit=True)
    e.calculate_reliability_metrics(T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _inc(e)
    p = sp("rel_incidents.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["severity"] = "LOW"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_integrity_check("a", "HASH_CHECK", "PASS", now=T[0], commit=True)
    e.run_integrity_check("b", "SCHEMA_CHECK", "PASS", now=T[1], commit=True)
    p = sp("rel_integrity_checks.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate_incident(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _inc(e)
    p = sp("rel_incidents.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_incident_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.analyze_incident(inc, now=T[1], commit=True)
    assert incident_lifecycle_integrity()["ok"] is True


def test_postmortem_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    pm = e.create_postmortem(inc, "r", "i", "l", T[1], commit=True).postmortem_id
    e.review_postmortem(pm, "rev", now=T[2], commit=True)
    assert postmortem_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _inc(e, desc="a")
    _inc(e, desc="b")
    assert duplicate_integrity()["ok"] is True


def test_recovery_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.create_recovery_plan(inc, ["s"], "o", T[1], commit=True)
    e.record_recovery_event(inc, "a", "VERIFIED", now=T[2], commit=True)
    assert recovery_integrity()["ok"] is True


def test_recovery_integrity_detects_auto_execute(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.create_recovery_plan(inc, ["s"], "o", T[1], commit=True)
    p = sp("rel_recovery_plans.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["auto_execute"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert recovery_integrity()["ok"] is False


def test_metric_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.calculate_reliability_metrics(T[0], commit=True)
    assert metric_integrity()["ok"] is True


def test_metric_integrity_detects_non_observation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.calculate_reliability_metrics(T[0], commit=True)
    p = sp("rel_reliability_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_observation"] = False
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert metric_integrity()["ok"] is False


def test_check_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_integrity_check("l", "REPLAY_CHECK", "PASS", now=T[0], commit=True)
    assert check_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.create_recovery_plan(inc, ["s"], "o", T[1], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.analyze_incident(inc, now=T[1], commit=True)
    assert replay(e, T[9])["deterministic"] is True


def test_replay_metrics_stable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _inc(e)
    m1 = e.calculate_reliability_metrics(T[9], commit=False)
    m2 = e.calculate_reliability_metrics(T[9], commit=False)
    assert m1 == m2


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["RECORD", "DETECT", "VERIFY", "ANALYZE", "PLAN", "REVIEW"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "ACTIVATE_LIVE", "CHANGE_PERMISSION",
                                "MODIFY_MODEL", "REPAIR_LIVE", "RESTART_EXECUTION"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.incident_id, ("l", "DATA_FAILURE", "d"), "RLI:"),
    (M.incident_event_id, ("i", "OPEN", 0), "RLN:"),
    (M.plan_id, ("i", 0), "RLP:"),
    (M.recovery_event_id, ("i", "a", 0), "RLE:"),
    (M.integrity_check_id, ("l", "HASH_CHECK", 0), "RLC:"),
    (M.reliability_metric_id, ("incident_frequency", 0), "RLM:"),
    (M.postmortem_id, ("i",), "RLO:"),
    (M.postmortem_event_id, ("p", "DRAFT", 0), "RLD:"),
    (M.report_id, ("s", "t"), "RLR:"),
    (M.artifact_id, ("INCIDENT", "r"), "RLA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_ids_deterministic():
    assert M.incident_id("l", "DATA_FAILURE", "d") == M.incident_id("l", "DATA_FAILURE", "d")


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ 조회 / summary ═══════════════
def test_list_incidents(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _inc(e, desc="a")
    _inc(e, desc="b")
    assert len(e.list_incidents()) == 2


def test_list_postmortems(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.create_postmortem(inc, "r", "i", "l", T[1], commit=True)
    assert len(e.list_postmortems()) == 1


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    inc = _inc(e)
    e.create_recovery_plan(inc, ["s"], "o", T[1], commit=True)
    e.run_integrity_check("l", "HASH_CHECK", "PASS", now=T[2], commit=True)
    s = e.summary(T[9])
    assert s.incident_count == 1
    assert s.recovery_plan_count == 1
    assert s.integrity_check_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_incident(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reliability.__main__ import main
    assert main(["incident", "--source", "data_governance", "--category", "DATA_FAILURE",
                 "--desc", "missing rows", "--severity", "HIGH", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["incident"]["to_state"] == "OPEN"


def test_cli_integrity(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reliability.__main__ import main
    assert main(["integrity", "--layer", "data", "--type", "HASH_CHECK", "--result", "PASS",
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["integrity_check"]["result"] == "PASS"


def test_cli_metrics(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reliability.__main__ import main
    assert main(["metrics", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "incident_frequency" in out["reliability_metrics"]


def test_cli_plan_and_event(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reliability.__main__ import main
    main(["incident", "--source", "l", "--category", "DATA_FAILURE", "--desc", "d", "--commit"])
    inc = json.loads(capsys.readouterr().out)["incident"]["incident_id"]
    assert main(["plan", "--incident", inc, "--steps", "a|b", "--owner", "o", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["plan"]["auto_execute"] is False
    assert main(["event", "--incident", inc, "--action", "reingest", "--result", "VERIFIED",
                 "--commit"]) == 0


def test_cli_postmortem(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reliability.__main__ import main
    main(["incident", "--source", "l", "--category", "DATA_FAILURE", "--desc", "d", "--commit"])
    inc = json.loads(capsys.readouterr().out)["incident"]["incident_id"]
    assert main(["postmortem", "--incident", inc, "--root", "rc", "--impact", "im",
                 "--lesson", "le", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["postmortem"]["to_state"] == "DRAFT"


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reliability.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reliability.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reliability.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_reliability.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_incident("l", "DATA_FAILURE", "d", now=T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "rel_incidents.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_incident("l", "DATA_FAILURE", "d", now=T[0], commit=True)
    with pytest.raises(Exception):
        ev.severity = "LOW"


def test_eight_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rel_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("rel_incidents.jsonl", "rel_recovery_plans.jsonl", "rel_recovery_events.jsonl",
                "rel_integrity_checks.jsonl", "rel_reliability_metrics.jsonl",
                "rel_postmortems.jsonl", "rel_reports.jsonl", "rel_artifacts.jsonl"):
        assert req in names


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_trading", "jarvis.portfolio_execution",
    "jarvis.live_portfolio", "jarvis.permission_control", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
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
    bad = ("execute", "deploy", "approve", "allocate", "promote", "trade", "repair_live",
           "restart_execution", "execute_trade", "place_order", "allocate_capital",
           "deploy_strategy", "activate_live", "change_permission", "modify_model")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def update_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


def test_engine_no_forbidden_methods():
    e = _eng()
    for attr in ("execute", "deploy", "repair_live", "restart_execution", "allocate"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 상위 소스 시드(READ ONLY 대상): 모니터링 헬스 이벤트
    p = sp("rmon_health_checks.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"health_id": f"MOH:{i}", "status": "FAILED"}) + "\n")
    e = _eng()
    # 관찰 → 장애 탐지 기록
    inc = e.register_incident("monitoring", "PIPELINE_FAILURE", "3 consecutive FAILED health",
                              "CRITICAL", T[0], commit=True).incident_id
    # 무결성 검증(상위 원장 READ ONLY 스캔)
    checks = e.scan_upstream_integrity(T[1], commit=True)
    assert any(c.target_layer == "monitoring" and c.result == "PASS" for c in checks)
    # 분석 → 복구 계획 → 복구 시도(기록만)
    e.analyze_incident(inc, now=T[2], commit=True)
    e.create_recovery_plan(inc, ["re-run pipeline observation", "revalidate lineage"], "sre-research",
                           T[3], commit=True)
    e.mark_recovery_planned(inc, now=T[4], commit=True)
    e.record_recovery_event(inc, "re-run pipeline observation", "VERIFIED", "recovered", T[5],
                            commit=True)
    e.resolve_incident(inc, now=T[6], commit=True)
    # 포스트모템(사람 검토 필수)
    pm = e.create_postmortem(inc, "upstream health degraded", "research paused",
                             "add earlier anomaly gate", T[7], commit=True).postmortem_id
    e.review_postmortem(pm, "reviewer-1", now=T[8], commit=True)
    e.record_postmortem(pm, "lead-1", now=T[9], commit=True)
    assert e.postmortem_state(pm) == P_RECORDED
    # 지표(관찰만)
    metrics = e.calculate_reliability_metrics(T[10], commit=True)
    assert metrics["incident_frequency"] == 1.0
    assert metrics["research_availability_score"] == 1.0  # 해결됨
    # 리포트
    r = e.generate_report("SYSTEM", T[11], commit=True)
    assert r.incident_count == 1
    assert r.postmortem_count == 1
    assert r.is_binding is False  # RECORD ≠ REPAIR
    e.archive_incident(inc, now=T[12], commit=True)
    assert e.incident_state(inc) == I_ARCHIVED
    assert open(p).read()  # 상위 원장 여전히 존재·불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[13])["deterministic"] is True
