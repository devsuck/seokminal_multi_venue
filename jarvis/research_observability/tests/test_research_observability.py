"""P10.18 Research Monitoring & Observability 테스트. **연구 시스템 건강 관찰 전용.**

건강 기록(불변·상태 검증)·지표(불변·유형 검증·집계)·스냅샷(결정적·중복)·이상(관찰 기록·범주/심각도 검증·
상태 추적)·활동 타임라인·품질 신호 이력·리포트(재현)·verify(체인/변조/중복/참조/스냅샷 일관성/전이/계보)·
replay·상위 READ ONLY 보호·CLI·보안(금지import·복구/실행/수정/재시작/배포 없음·상위 원장 무변경·삭제 API
없음·불변·OBSERVATION≠ACTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_observability import ledger
from jarvis.research_observability import models as M
from jarvis.research_observability.engine import ResearchObservabilityEngine
from jarvis.research_observability.models import (
    ACKNOWLEDGED,
    ARCHIVED,
    CLEARED,
    DEGRADED,
    HEALTHY,
    OBSERVED,
    UNKNOWN,
    WARNING,
    IllegalTransition,
    ImmutableHealthError,
    ImmutableMetricError,
    InvalidAnomalyCategory,
    InvalidHealthStatus,
    InvalidMetricType,
    UnknownAnomaly,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"validation_rate": 0.9, "reproducibility_score": 0.9, "data_quality_score": 0.85,
       "workflow_health": 0.9, "failure_rate": 0.05}
_LO = {"validation_rate": 0.2, "reproducibility_score": 0.1, "data_quality_score": 0.2,
       "workflow_health": 0.2, "failure_rate": 0.8}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_observability.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchObservabilityEngine()


def _metric(eng, mt=None, val=0.9, src="research_governance:ST1", epoch="E1", commit=True):
    return eng.register_metric(mt or M.M_VALIDATION_RATE, val, src, epoch, T0, commit=commit)


def _health(eng, layer="research_governance", status="", metrics=None, epoch="E1", commit=True):
    return eng.record_health(layer, status, metrics if metrics is not None else _HI, epoch, T0,
                             commit=commit)


def _anomaly(eng, src="research_governance:ST1", cat=None, sev="HIGH", epoch="E1", commit=True):
    return eng.record_anomaly(src, cat or M.A_SUDDEN_QUALITY_DROP, sev, ["ev1"], epoch, T0,
                              commit=commit)


def _full(eng):
    """metric→health→snapshot→anomaly→activity→quality→report end-to-end."""
    m = _metric(eng)
    h = _health(eng)
    s = eng.create_snapshot("snap1", "E1", [m.metric_id], {"research_governance": HEALTHY}, T0,
                            commit=True)
    a = _anomaly(eng)
    eng.track_activity("research_governance", M.ACT_METRIC_RECORDED, m.metric_id, "d", T0,
                       commit=True)
    eng.record_quality_signal("research_governance:ST1", M.M_DATA_QUALITY_SCORE, 0.8, "E1", "ok",
                              T0, commit=True)
    eng.generate_report("GLOBAL", _HI, T1, commit=True)
    return m, h, s, a


# ── Metric ──
def test_metric_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _metric(_eng())
    assert m.metric_id.startswith("MHM:")
    assert m.metric_type == M.M_VALIDATION_RATE
    assert m.value == 0.9


def test_metric_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidMetricType):
        _eng().register_metric("not_a_metric", 1.0, "x", "E1", T0, commit=True)


def test_metric_all_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, mt in enumerate(M.METRIC_TYPES):
        m = eng.register_metric(mt, 0.5, f"src{i}", "E1", T0, commit=True)
        assert m.metric_type == mt
    assert len(ledger.read_metrics()) == len(M.METRIC_TYPES)


def test_metric_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _metric(eng)
    b = _metric(eng)
    assert a.metric_id == b.metric_id
    assert len(ledger.read_metrics()) == 1


def test_metric_immutable_value(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _metric(eng, val=0.9)
    with pytest.raises(ImmutableMetricError):
        _metric(eng, val=0.5)


def test_metric_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _metric(_eng())
    assert m.metric_id == M.metric_id(M.M_VALIDATION_RATE, "research_governance:ST1", "E1")


def test_metric_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _metric(_eng(), commit=False)
    assert ledger.read_metrics() == []


def test_metric_aggregation_failure_frequency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_metric(M.M_FAILURE_RATE, 0.2, "s1", "E1", T0, commit=True)
    eng.register_metric(M.M_FAILURE_RATE, 0.4, "s2", "E1", T0, commit=True)
    res = eng.failure_frequency()
    assert res["samples"] == 2
    assert abs(res["avg_failure_rate"] - 0.3) < 1e-9


def test_metric_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _metric(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_METRIC, m.metric_id))


# ── Health ──
def test_health_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _health(_eng())
    assert h.health_id.startswith("MHH:")
    assert h.status == HEALTHY
    assert h.source_layer == "research_governance"


def test_health_derived_status(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _health(_eng(), metrics=_LO)
    assert h.status == DEGRADED


def test_health_explicit_status(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _health(_eng(), status=WARNING, metrics={})
    assert h.status == WARNING


def test_health_unknown_when_no_metrics(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _eng().record_health("layerX", "", {}, "E1", T0, commit=True)
    assert h.status == UNKNOWN


def test_health_invalid_status(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidHealthStatus):
        _eng().record_health("layerX", "SUPER_BAD", {}, "E1", T0, commit=True)


def test_health_all_states_valid(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, st in enumerate(M.HEALTH_STATES):
        h = eng.record_health(f"layer{i}", st, {}, "E1", T0, commit=True)
        assert h.status == st


def test_health_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _health(eng, metrics=_HI)
    with pytest.raises(ImmutableHealthError):
        _health(eng, metrics=_LO)


def test_health_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _health(eng)
    b = _health(eng)
    assert a.health_id == b.health_id
    assert len(ledger.read_health()) == 1


def test_health_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _health(_eng())
    assert h.health_id == M.health_id("research_governance", "E1")


def test_health_records_layer_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _health(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_LAYER, "research_governance"))
    ha = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == h.health_id and a["artifact_type"] == M.ART_HEALTH)
    assert ha["parent_artifact"] == M.artifact_id(M.ART_LAYER, "research_governance")


def test_health_score_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _health(_eng(), metrics=_HI)
    assert h.health_score > 0.7


# ── Snapshot ──
def test_snapshot_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("snap1", "E1", ["MHM:a", "MHM:b"], {"L": HEALTHY}, T0, commit=True)
    assert s.snapshot_id.startswith("MHS:")
    assert s.metric_count == 2


def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.create_snapshot("snap1", "E1", ["m2", "m1"], {"L": HEALTHY}, T0, commit=False)
    b = eng.create_snapshot("snap1", "E1", ["m1", "m2"], {"L": HEALTHY}, T0, commit=False)
    assert a.snapshot_hash == b.snapshot_hash
    assert a.collected_metrics == b.collected_metrics == ["m1", "m2"]


def test_snapshot_duplicate_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_snapshot("snap1", "E1", ["m1"], {}, T0, commit=True)
    eng.create_snapshot("snap1", "E1", ["m1"], {}, T0, commit=True)
    assert len(ledger.read_snapshots()) == 1


def test_snapshot_different_epochs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s1 = eng.create_snapshot("snap1", "E1", ["m1"], {}, T0, commit=True)
    s2 = eng.create_snapshot("snap1", "E2", ["m1"], {}, T0, commit=True)
    assert s1.snapshot_id != s2.snapshot_id
    assert len(ledger.read_snapshots()) == 2


def test_snapshot_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("snap1", "E1", [], {}, T0, commit=True)
    assert s.snapshot_id == M.snapshot_id("snap1", "E1")


def test_snapshot_parent_links_metric(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = _metric(eng)
    s = eng.create_snapshot("snap1", "E1", [m.metric_id], {}, T0, commit=True)
    sa = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == s.snapshot_id and a["artifact_type"] == M.ART_SNAPSHOT)
    assert sa["parent_artifact"] == M.artifact_id(M.ART_METRIC, m.metric_id)


# ── Anomaly ──
def test_anomaly_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _anomaly(_eng())
    assert a.anomaly_id.startswith("MHA:")
    assert a.to_state == OBSERVED
    assert a.category == M.A_SUDDEN_QUALITY_DROP


def test_anomaly_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidAnomalyCategory):
        _eng().record_anomaly("s", "not_a_cat", "LOW", [], "E1", T0, commit=True)


def test_anomaly_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, cat in enumerate(M.ANOMALY_CATEGORIES):
        a = eng.record_anomaly(f"s{i}", cat, "MEDIUM", [], "E1", T0, commit=True)
        assert a.category == cat
    assert len(ledger.distinct_anomalies()) == len(M.ANOMALY_CATEGORIES)


def test_anomaly_severity_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    for sev in M.SEVERITIES:
        pass
    a = _anomaly(_eng(), sev="CRITICAL")
    assert a.severity == "CRITICAL"


def test_anomaly_state_tracking(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _anomaly(eng)
    eng.transition_anomaly(a.anomaly_id, ACKNOWLEDGED, T1, commit=True)
    assert eng.anomaly_state(a.anomaly_id) == ACKNOWLEDGED


def test_anomaly_clear(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _anomaly(eng)
    eng.clear_anomaly(a.anomaly_id, T1, commit=True)
    assert eng.anomaly_state(a.anomaly_id) == CLEARED


def test_anomaly_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _anomaly(eng)
    eng.transition_anomaly(a.anomaly_id, CLEARED, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_anomaly(a.anomaly_id, OBSERVED, T2, commit=True)


def test_anomaly_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownAnomaly):
        _eng().transition_anomaly("MHA:nope", CLEARED, T1, commit=True)


def test_anomaly_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _anomaly(eng)
    b = _anomaly(eng)
    assert a.anomaly_id == b.anomaly_id
    assert len(ledger.distinct_anomalies()) == 1


def test_anomaly_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _anomaly(_eng())
    assert a.anomaly_id == M.anomaly_id("research_governance:ST1", M.A_SUDDEN_QUALITY_DROP, "E1")


def test_anomaly_can_transition_table():
    assert M.can_transition_anomaly("", OBSERVED)
    assert M.can_transition_anomaly(OBSERVED, ACKNOWLEDGED)
    assert M.can_transition_anomaly(ACKNOWLEDGED, CLEARED)
    assert not M.can_transition_anomaly(CLEARED, OBSERVED)


def test_anomaly_no_response_field(tmp_path, monkeypatch):
    """이상 레코드에 response/action/recover 필드가 없어야 한다(자동 대응 없음)."""
    _iso(tmp_path, monkeypatch)
    a = _anomaly(_eng())
    d = a.to_dict()
    for banned in ("response", "action", "recover", "auto_fix"):
        assert banned not in d


# ── Activity / Quality ──
def test_activity_track(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _eng().track_activity("scope", M.ACT_METRIC_RECORDED, "ref1", "d", T0, commit=True)
    assert t.activity_id.startswith("MHT:")
    assert len(ledger.read_activity()) == 1


def test_activity_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _eng().track_activity("scope", "TYPE", "ref", "", T0, commit=True)
    assert t.activity_id == M.activity_id("scope", "TYPE", "ref")


def test_quality_signal_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    q = _eng().record_quality_signal("src:ST1", M.M_DATA_QUALITY_SCORE, 0.8, "E1", "ok", T0,
                                     commit=True)
    assert q.quality_id.startswith("MHQ:")
    assert q.value == 0.8


def test_quality_trend(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_quality_signal("src:ST1", M.M_DATA_QUALITY_SCORE, 0.5, "E1", "", T0, commit=True)
    eng.record_quality_signal("src:ST1", M.M_DATA_QUALITY_SCORE, 0.8, "E2", "", T1, commit=True)
    tr = eng.quality_trend("src:ST1")
    assert tr["samples"] == 2
    assert abs(tr["delta"] - 0.3) < 1e-9


def test_quality_trend_single(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_quality_signal("src:ST1", M.M_DATA_QUALITY_SCORE, 0.5, "E1", "", T0, commit=True)
    assert eng.quality_trend("src:ST1")["delta"] == 0.0


# ── Health score / analyze ──
def test_health_score_high():
    assert M.health_score(_HI) > 0.7


def test_health_score_low():
    assert M.health_score(_LO) < 0.4


def test_health_score_failure_inverse():
    # failure_rate 0.0 -> inverse 1.0 contributes 0.10
    s = M.health_score({"failure_rate": 0.0})
    assert abs(s - 0.10) < 1e-9


def test_health_weights_sum_one():
    assert abs(sum(M.HEALTH_WEIGHTS.values()) - 1.0) < 1e-9


def test_health_status_labels():
    assert M.health_status(_HI) == HEALTHY
    assert M.health_status(_LO) == DEGRADED
    assert M.health_status({"validation_rate": 1.0, "reproducibility_score": 1.0}) == WARNING


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HI)
    assert res["health_status"] == HEALTHY
    assert res["health_score"] > 0.7


def test_severity_weight():
    assert M.severity_weight("CRITICAL") == 1.0
    assert M.severity_weight("???") == 0.0


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.report_id.startswith("MHR:")
    assert r.metric_count >= 1
    assert r.health_record_count >= 1
    assert r.anomaly_count >= 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    a = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    b = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert M.M_VALIDATION_RATE in r.metric_type_distribution
    assert HEALTHY in r.health_status_distribution


def test_report_degradation_indicators(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_health("bad_layer", "", _LO, "E1", T0, commit=True)
    _anomaly(eng, sev="CRITICAL")
    r = eng.generate_report("GLOBAL", _HI, T1, commit=True)
    assert any("degraded_health" in d for d in r.degradation_indicators)
    assert any("open_anomaly" in d for d in r.degradation_indicators)


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert "OBSERVATION ≠ ACTION" in r.disclaimer


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("GLOBAL", _HI, T0, commit=True)
    eng.generate_report("GLOBAL", _HI, T0, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    d = r.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d, ensure_ascii=False).lower()
    for verb in ("buy", "sell", "place_order", "deploy", "allocate_capital"):
        assert verb not in blob


def test_report_anomaly_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _anomaly(eng)
    eng.clear_anomaly(a.anomaly_id, T1, commit=True)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.anomaly_state_distribution.get(CLEARED) == 1


# ── Lineage / verify ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    h = _health(eng)
    anc = eng.trace_lineage(M.artifact_id(M.ART_HEALTH, h.health_id))
    assert M.artifact_id(M.ART_LAYER, "research_governance") in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_observability.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _metric(eng)
    p = sp("mh_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["value"] = 0.123
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_observability.verify import verify_ledger
    assert verify_ledger(ledger.METRICS)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_metric(M.M_FAILURE_RATE, 0.1, "s1", "E1", T0, commit=True)
    eng.register_metric(M.M_FAILURE_RATE, 0.2, "s2", "E1", T0, commit=True)
    p = sp("mh_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_observability.verify import verify_ledger
    assert verify_ledger(ledger.METRICS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _metric(eng)
    p = sp("mh_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_observability.verify import verify_ledger
    assert verify_ledger(ledger.METRICS)["ok"] is False


def test_verify_snapshot_consistency_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_snapshot("snap1", "E1", ["m1", "m2"], {"L": HEALTHY}, T0, commit=True)
    from jarvis.research_observability.verify import snapshot_consistency
    assert snapshot_consistency()["ok"] is True


def test_verify_detects_inconsistent_snapshot(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_snapshot("snap1", "E1", ["m1"], {"L": HEALTHY}, T0, commit=True)
    p = sp("mh_snapshots.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["collected_metrics"] = ["m1", "TAMPERED"]  # hash no longer matches
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_observability.verify import snapshot_consistency
    res = snapshot_consistency()
    assert res["ok"] is False
    assert any("inconsistent_snapshot" in i for i in res["issues"])


def test_verify_anomaly_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _anomaly(eng)
    eng.clear_anomaly(a.anomaly_id, T1, commit=True)
    from jarvis.research_observability.verify import anomaly_transition_validation
    assert anomaly_transition_validation()["ok"] is True


def test_verify_detects_bad_anomaly_transition(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _anomaly(eng)
    p = sp("mh_anomalies.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["to_state"] = "CLEARED"  # illegal from GENESIS
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_observability.verify import anomaly_transition_validation
    assert anomaly_transition_validation()["ok"] is False


def test_verify_reference_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _health(eng)
    from jarvis.research_observability.models import content_hash
    rec = {"artifact_id": "MHX:broken", "artifact_type": "HEALTH", "ref_id": "x",
           "parent_artifact": "MHX:ghost", "created_at": T0, "input_hash": "", "record_hash": "",
           "previous_hash": ledger.artifacts_head()["record_hash"]}
    rec["record_hash"] = content_hash(rec)
    ledger.append_artifact(rec)
    from jarvis.research_observability.verify import reference_validation
    assert reference_validation()["ok"] is False


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_observability.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["anomaly_transitions"]["ok"] is True
    assert res["snapshot"]["ok"] is True
    assert res["reference"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _metric(eng)
    from jarvis.research_observability.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "MHX:c1", "artifact_type": "METRIC", "ref_id": "x1",
          "parent_artifact": "MHX:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "MHX:c2", "artifact_type": "METRIC", "ref_id": "x2",
          "parent_artifact": "MHX:c1", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": a1["record_hash"]}
    a2["record_hash"] = content_hash(a2)
    ledger.append_artifact(a2)
    res = eng.verify_lineage()
    assert res["ok"] is False
    assert any("cycle" in i for i in res["issues"])


# ── replay / summary ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_observability.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert s.metric_count >= 1
    assert s.health_record_count >= 1
    assert s.snapshot_count >= 1
    assert s.anomaly_count >= 1
    assert s.activity_count >= 1
    assert s.quality_signal_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


# ── 상위 READ ONLY ──
def test_list_source_objects_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("research_governance") == []


def test_list_source_objects_reads(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rg_strategies.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
        f.write(json.dumps({"strategy_id": "ST2"}) + "\n")
    out = _eng().list_source_objects("research_governance")
    assert out == ["research_governance:ST1", "research_governance:ST2"]


def test_source_read_only_no_write(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    src = sp("rg_strategies.jsonl")
    with open(src, "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
    before = open(src).read()
    eng = _eng()
    _full(eng)
    eng.list_source_objects("research_governance")
    assert open(src).read() == before


def test_unknown_source_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("nonexistent") == []


def test_source_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rg_strategies.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
    assert ledger.source_count("research_governance") == 1
    assert ledger.source_count("nope") == 0


def test_observatory_source_is_ob_prefixed_read_only():
    """P10.10 ob_ 원장은 READ ONLY 소스로만 참조(소유 아님)."""
    spec = ledger.SOURCE_LEDGERS.get("research_observatory")
    assert spec is not None
    assert spec[0].startswith("ob_")


# ── CLI ──
def test_cli_metric(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.__main__ import main
    rc = main(["metric", "--metric-type", "validation_rate", "--value", "0.9", "--source",
               "rg:ST1", "--epoch", "E1", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["metric"]["metric_id"].startswith("MHM:")


def test_cli_health(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.__main__ import main
    rc = main(["health", "--source-layer", "research_governance", "--metrics-json",
               json.dumps(_HI), "--epoch", "E1", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["health"]["status"] == HEALTHY


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.__main__ import main
    rc = main(["snapshot", "--name", "snap1", "--epoch", "E1", "--metrics", "m1,m2", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["snapshot"]["snapshot_id"].startswith("MHS:")


def test_cli_anomaly(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.__main__ import main
    rc = main(["anomaly", "--source", "rg:ST1", "--category", "missing_data", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["anomaly"]["anomaly_id"].startswith("MHA:")


def test_cli_activity(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.__main__ import main
    rc = main(["activity", "--scope", "s", "--activity-type", "METRIC_RECORDED", "--reference",
               "r", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["activity"]["activity_id"].startswith("MHT:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.__main__ import main
    rc = main(["report", "--metrics-json", json.dumps(_HI), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("MHR:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.__main__ import main
    main(["metric", "--metric-type", "failure_rate", "--value", "0.1", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.__main__ import main
    main(["metric", "--metric-type", "failure_rate", "--value", "0.1", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observability.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "metric_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_observability.engine as eng_mod
    import jarvis.research_observability.models as mdl_mod
    import jarvis.research_observability.ledger as led_mod
    import jarvis.research_observability.verify as ver_mod
    import jarvis.research_observability.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "modify_strategy(", "auto_fix(", "auto_recover(",
                 "restart_workflow("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.research_observability.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def deploy", "def trade", "def place_order",
               "def allocate_capital", "def modify_strategy", "def auto_fix",
               "def auto_recover", "def restart_workflow"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchObservabilityEngine))
    for banned in ("execute", "deploy", "trade", "place_order", "allocate_capital",
                   "modify_strategy", "auto_fix", "auto_recover", "restart_workflow"):
        assert banned not in api


def test_observation_not_action(tmp_path, monkeypatch):
    """건강 레코드에 action/recover/fix/execute 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    h = _health(_eng())
    d = h.to_dict()
    for banned in ("action", "recover", "fix", "execute", "restart"):
        assert banned not in d


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_autonomy_unchanged(tmp_path, monkeypatch):
    import jarvis.config as _cfg
    before = _cfg.AUTONOMY_LEVEL
    _iso(tmp_path, monkeypatch)
    _full(_eng())
    assert _cfg.AUTONOMY_LEVEL == before
    assert _cfg.live_execution_enabled() is False


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.research_observability.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_mh(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("mh_")


def test_no_ob_prefix_ownership():
    """P10.18 은 ob_ 원장을 소유하지 않는다(P10.10 소유 경계 보존)."""
    for fn, _idf in ledger.ALL_LEDGERS:
        assert not fn.startswith("ob_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 8


def test_engine_no_upstream_layer_import():
    import jarvis.research_observability.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.research_observatory", "import jarvis.research_orchestration",
               "import jarvis.research_evolution", "import jarvis.meta_intelligence"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.health_id("a", "e")[:4],
        M.metric_id("a", "b", "e")[:4],
        M.snapshot_id("a", "e")[:4],
        M.anomaly_id("a", "b", "e")[:4],
        M.anomaly_event_id("a", "", OBSERVED)[:4],
        M.activity_id("a", "b", "c")[:4],
        M.quality_id("a", "e")[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 9


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_metrics_hash_order_independent():
    assert M.metrics_hash({"a": 1, "b": 2}) == M.metrics_hash({"b": 2, "a": 1})


def test_snapshot_hash_sorts_metrics():
    assert M.snapshot_hash(["b", "a"], {}) == M.snapshot_hash(["a", "b"], {})


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_health_states_count():
    assert len(M.HEALTH_STATES) == 4


def test_metric_types_count():
    assert len(M.METRIC_TYPES) == 6


def test_anomaly_categories_count():
    assert len(M.ANOMALY_CATEGORIES) == 5


def test_anomaly_states_count():
    assert len(M.ANOMALY_STATES) == 4


def test_node_types_count():
    assert len(M.NODE_TYPES) == 5


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _metric(eng, commit=False)
    _health(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_health_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _health(_eng())
    d = h.to_dict()
    assert d["health_id"] == h.health_id
    assert set(("source_layer", "status", "metrics")).issubset(d)


def test_report_metrics_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert r.metrics == _HI


def test_multiple_scopes_distinct_reports(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("A", _HI, T0, commit=True)
    eng.generate_report("B", _HI, T0, commit=True)
    assert len(ledger.read_reports()) == 2


def test_metric_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _metric(_eng())
    assert m.input_hash == M.input_digest(M.M_VALIDATION_RATE, "research_governance:ST1", "E1")


def test_anomaly_evidence_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _anomaly(_eng())
    assert a.evidence == ["ev1"]


def test_snapshot_health_summary_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("s1", "E1", ["m1"], {"L": WARNING}, T0, commit=True)
    assert s.health_summary == {"L": WARNING}


def test_summary_state_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert HEALTHY in s.health_status_distribution
    assert OBSERVED in s.anomaly_state_distribution


def test_degradation_indicators_empty_when_healthy(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _health(eng, metrics=_HI)
    assert eng.degradation_indicators() == []


def test_source_ledgers_not_mh_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("mh_")
        assert isinstance(idf, str)


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m1 = _metric(eng, src="a")
    m2 = _metric(eng, src="b")
    assert m1.metric_id != m2.metric_id
    assert len(ledger.read_metrics()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    for phrase in ("OBSERVATION ≠ ACTION", "DETECTION ≠ CORRECTION", "WARNING ≠ INTERVENTION",
                   "MONITORING ≠ EXECUTION"):
        assert phrase in r.disclaimer


def test_health_score_partial_metrics():
    s = M.health_score({"validation_rate": 1.0, "reproducibility_score": 1.0})
    assert abs(s - (0.25 + 0.25)) < 1e-9


def test_quality_signal_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    q = _eng().record_quality_signal("src", M.M_DATA_QUALITY_SCORE, 0.5, "E1", "", T0, commit=True)
    assert q.quality_id == M.quality_id("src:" + M.M_DATA_QUALITY_SCORE, "E1")
