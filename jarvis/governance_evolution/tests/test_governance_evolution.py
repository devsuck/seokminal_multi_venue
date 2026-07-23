"""P10.22 Research Governance Evolution Intelligence 테스트. **거버넌스 생태계 시간적 변화 분석 전용.**

진화 이벤트(불변·유형)·거버넌스 상태(타임라인·성숙도 전이·회귀)·성숙도 평가(결정적 점수·불변)·변화 패턴
(탐지·신뢰도)·역사적 비교(diff)·스냅샷(결정적 해시·중복)·리포트(결정적)·verify(체인/변조/중복/전이/타임라인/
계보)·replay·상위 READ ONLY 보호·CLI·보안(금지import·업그레이드/실행/승인/배포 없음·상위 원장 무변경·삭제
API 없음·불변·EVOLUTION ANALYSIS≠ACTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.governance_evolution import ledger
from jarvis.governance_evolution import models as M
from jarvis.governance_evolution.engine import GovernanceEvolutionEngine
from jarvis.governance_evolution.models import (
    DEFINED,
    DEVELOPING,
    INITIAL,
    MANAGED,
    OPTIMIZING,
    IllegalTransition,
    ImmutableEventError,
    ImmutableMaturityError,
    InvalidEventType,
    InvalidMaturityLevel,
    UnknownState,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"maturity_growth": 0.9, "capability_expansion": 0.85, "change_stability": 0.8,
       "regression_rate": 0.1, "assessment_coverage": 0.9}
_LO = {"maturity_growth": 0.1, "capability_expansion": 0.2, "change_stability": 0.1,
       "regression_rate": 0.9, "assessment_coverage": 0.2}
_DIMS = {"data_quality": 0.9, "reproducibility": 0.8, "transparency": 0.85,
         "validation_strength": 0.9, "governance_depth": 0.8, "auditability": 0.85}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.governance_evolution.ledger.state_path", sp)
    return sp


def _eng():
    return GovernanceEvolutionEngine()


def _event(eng, layer="research_compliance", et=None, desc="added OOS gate", commit=True):
    return eng.record_event(layer, et or M.E_CAPABILITY_ADDED, desc, T0, commit=commit)


def _state(eng, layer="research_compliance", level=INITIAL, caps=None, commit=True):
    return eng.create_state(layer, level, caps or ["baseline"], T0, commit=commit)


def _full(eng):
    """event→state(x2 timeline)→maturity→pattern→compare→snapshot→report end-to-end."""
    _event(eng)
    s1 = eng.create_state("research_compliance", INITIAL, ["c1"], T0, commit=True)
    s2 = eng.create_state("research_compliance", DEVELOPING, ["c1", "c2"], T1, commit=True)
    eng.assess_maturity("research_compliance", _DIMS, "ev1", "E1", T0, commit=True)
    eng.analyze_pattern([M.E_CAPABILITY_ADDED], None, T0, commit=True)
    eng.compare_states(s1.event_id, s2.event_id, T1, commit=True)
    eng.create_snapshot("snap1", "E1", [s1.event_id, s2.event_id], {"layers": 1}, T0, commit=True)
    eng.generate_report("GLOBAL", _HI, T2, commit=True)
    return s1, s2


# ── Evolution Event ──
def test_event_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _event(_eng())
    assert e.event_id.startswith("GEE:")
    assert e.event_type == M.E_CAPABILITY_ADDED


def test_event_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidEventType):
        _eng().record_event("L", "not_a_type", "d", T0, commit=True)


def test_event_all_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, et in enumerate(M.EVENT_TYPES):
        e = eng.record_event("L", et, f"d{i}", T0, commit=True)
        assert e.event_type == et
    assert len(ledger.read_events()) == len(M.EVENT_TYPES)


def test_event_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _event(eng)
    b = _event(eng)
    assert a.event_id == b.event_id
    assert len(ledger.read_events()) == 1


def test_event_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    # same id (layer+type+description) but different metadata is impossible since
    # metadata derives from type+description; assert idempotency preserves first
    a = _event(eng)
    b = _event(eng)
    assert a.metadata_hash == b.metadata_hash


def test_event_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _event(_eng())
    assert e.event_id == M.event_id("research_compliance", M.E_CAPABILITY_ADDED, "added OOS gate")


def test_event_records_layer_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _event(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_LAYER, "research_compliance"))
    ea = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == e.event_id and a["artifact_type"] == M.ART_EVENT)
    assert ea["parent_artifact"] == M.artifact_id(M.ART_LAYER, "research_compliance")


def test_event_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _event(_eng(), commit=False)
    assert ledger.read_events() == []


# ── Governance State ──
def test_state_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _state(_eng())
    assert s.event_id.startswith("GSE:")
    assert s.state_id.startswith("GSX:")
    assert s.to_maturity == INITIAL
    assert s.sequence == 1


def test_state_invalid_level(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidMaturityLevel):
        _eng().create_state("L", "SUPREME", [], T0, commit=True)


def test_state_timeline_ordering(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", INITIAL, [], T0, commit=True)
    eng.create_state("L", DEVELOPING, [], T1, commit=True)
    s3 = eng.create_state("L", DEFINED, [], T2, commit=True)
    assert s3.sequence == 3
    assert eng.maturity_trajectory("L") == [INITIAL, DEVELOPING, DEFINED]


def test_state_transition_skip_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", INITIAL, [], T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.create_state("L", MANAGED, [], T1, commit=True)  # skips DEVELOPING, DEFINED


def test_state_first_any_level(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.create_state("L", DEFINED, [], T0, commit=True)  # first can be any
    assert s.to_maturity == DEFINED


def test_state_regression_tracked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", DEVELOPING, [], T0, commit=True)
    s = eng.create_state("L", INITIAL, [], T1, commit=True)  # regression allowed
    assert s.regression is True
    assert "L:DEVELOPING->INITIAL" in eng.regression_indicators()


def test_state_current_maturity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", INITIAL, [], T0, commit=True)
    eng.create_state("L", DEVELOPING, [], T1, commit=True)
    assert eng.current_maturity("L") == DEVELOPING


def test_state_capabilities_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _state(_eng(), caps=["a", "b"])
    assert s.capabilities == ["a", "b"]


def test_state_can_transition_table():
    assert M.can_transition_state("", INITIAL)
    assert M.can_transition_state("", OPTIMIZING)  # first any
    assert M.can_transition_state(INITIAL, DEVELOPING)
    assert M.can_transition_state(DEVELOPING, INITIAL)  # regression adjacent
    assert not M.can_transition_state(INITIAL, DEFINED)  # skip
    assert not M.can_transition_state(INITIAL, "SUPREME")


def test_state_parent_links_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _state(eng)
    sa = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == s.event_id and a["artifact_type"] == M.ART_STATE)
    assert sa["parent_artifact"] == M.artifact_id(M.ART_LAYER, "research_compliance")


def test_level_index_and_regression():
    assert M.level_index(INITIAL) == 0
    assert M.level_index(OPTIMIZING) == 4
    assert M.is_regression(DEVELOPING, INITIAL) is True
    assert M.is_regression(INITIAL, DEVELOPING) is False


# ── Maturity Assessment ──
def test_maturity_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().assess_maturity("L", _DIMS, "ev1", "E1", T0, commit=True)
    assert m.assessment_id.startswith("GEM:")
    assert 0.0 < m.overall_score <= 1.0


def test_maturity_deterministic_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().assess_maturity("L", {"data_quality": 1.0}, "", "E1", T0, commit=True)
    # only one dim set -> 1/6 weight (rounded to 8 decimals)
    assert abs(m.overall_score - (1.0 / 6)) < 1e-6


def test_maturity_full_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().assess_maturity("L", {d: 1.0 for d in M.MATURITY_DIMENSIONS}, "", "E1", T0,
                               commit=True)
    assert abs(m.overall_score - 1.0) < 1e-9


def test_maturity_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.assess_maturity("L", _DIMS, "", "E1", T0, commit=True)
    with pytest.raises(ImmutableMaturityError):
        eng.assess_maturity("L", {"data_quality": 0.1}, "", "E1", T0, commit=True)


def test_maturity_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.assess_maturity("L", _DIMS, "", "E1", T0, commit=True)
    b = eng.assess_maturity("L", _DIMS, "", "E1", T0, commit=True)
    assert a.assessment_id == b.assessment_id
    assert len(ledger.read_maturity()) == 1


def test_maturity_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().assess_maturity("L", _DIMS, "", "E1", T0, commit=True)
    assert m.assessment_id == M.maturity_id("L", "E1")


def test_maturity_different_epochs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.assess_maturity("L", _DIMS, "", "E1", T0, commit=True)
    b = eng.assess_maturity("L", _DIMS, "", "E2", T0, commit=True)
    assert a.assessment_id != b.assessment_id


def test_average_maturity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.assess_maturity("L1", {"data_quality": 1.0}, "", "E1", T0, commit=True)
    eng.assess_maturity("L2", {"data_quality": 1.0}, "", "E1", T0, commit=True)
    assert abs(eng.average_maturity() - (1.0 / 6)) < 1e-6


def test_overall_maturity_helper():
    assert M.overall_maturity({}) == 0.0
    assert abs(M.overall_maturity({d: 1.0 for d in M.MATURITY_DIMENSIONS}) - 1.0) < 1e-9


# ── Evolution Pattern ──
def test_pattern_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().analyze_pattern([M.E_CAPABILITY_ADDED, M.E_MATURITY_SHIFT], 2, T0, commit=True)
    assert p.pattern_id.startswith("GEP:")
    assert p.frequency == 2


def test_pattern_confidence_calculation():
    assert M.pattern_confidence(3, 3) == 1.0
    assert M.pattern_confidence(0, 0) == 0.0
    assert abs(M.pattern_confidence(3, 0) - 0.6) < 1e-9


def test_pattern_auto_frequency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_event("L1", M.E_CAPABILITY_ADDED, "d1", T0, commit=True)
    eng.record_event("L2", M.E_MATURITY_SHIFT, "d2", T0, commit=True)
    # consecutive [capability_added, maturity_shift] appears once
    p = eng.analyze_pattern([M.E_CAPABILITY_ADDED, M.E_MATURITY_SHIFT], None, T0, commit=True)
    assert p.frequency == 1


def test_pattern_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.analyze_pattern([M.E_CAPABILITY_ADDED], 1, T0, commit=True)
    b = eng.analyze_pattern([M.E_CAPABILITY_ADDED], 1, T0, commit=True)
    assert a.pattern_id == b.pattern_id
    assert len(ledger.read_patterns()) == 1


def test_pattern_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().analyze_pattern([M.E_CAPABILITY_ADDED], 1, T0, commit=True)
    assert p.pattern_id == M.pattern_id([M.E_CAPABILITY_ADDED])


def test_pattern_sequence_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().analyze_pattern(["a", "b", "c"], 1, T0, commit=True)
    assert p.detected_sequence == ["a", "b", "c"]


# ── Historical Comparison ──
def test_compare_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s1 = eng.create_state("L", INITIAL, ["c1"], T0, commit=True)
    s2 = eng.create_state("L", DEVELOPING, ["c1", "c2"], T1, commit=True)
    c = eng.compare_states(s1.event_id, s2.event_id, T1, commit=True)
    assert c.comparison_id.startswith("GEC:")
    assert c.differences["maturity_delta"] == 1
    assert c.differences["capabilities_added"] == ["c2"]


def test_compare_regression_diff(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s1 = eng.create_state("L", DEVELOPING, ["c1", "c2"], T0, commit=True)
    s2 = eng.create_state("L", INITIAL, ["c1"], T1, commit=True)
    c = eng.compare_states(s1.event_id, s2.event_id, T1, commit=True)
    assert c.differences["maturity_delta"] == -1
    assert c.differences["regression"] is True
    assert c.differences["capabilities_removed"] == ["c2"]


def test_compare_unknown_previous(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s2 = eng.create_state("L", INITIAL, [], T0, commit=True)
    with pytest.raises(UnknownState):
        eng.compare_states("GSE:ghost", s2.event_id, T1, commit=True)


def test_compare_unknown_current(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s1 = eng.create_state("L", INITIAL, [], T0, commit=True)
    with pytest.raises(UnknownState):
        eng.compare_states(s1.event_id, "GSE:ghost", T1, commit=True)


def test_compare_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s1 = eng.create_state("L", INITIAL, [], T0, commit=True)
    s2 = eng.create_state("L", DEVELOPING, [], T1, commit=True)
    eng.compare_states(s1.event_id, s2.event_id, T1, commit=True)
    eng.compare_states(s1.event_id, s2.event_id, T1, commit=True)
    assert len(ledger.read_comparisons()) == 1


# ── Snapshot ──
def test_snapshot_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("snap1", "E1", ["a", "b"], {"k": 1}, T0, commit=True)
    assert s.snapshot_id.startswith("GEN:")
    assert s.state_count == 2


def test_snapshot_deterministic_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.create_snapshot("snap1", "E1", ["b", "a"], {"k": 1}, T0, commit=False)
    b = eng.create_snapshot("snap1", "E1", ["a", "b"], {"k": 1}, T0, commit=False)
    assert a.snapshot_hash == b.snapshot_hash
    assert a.collected_states == b.collected_states == ["a", "b"]


def test_snapshot_duplicate_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_snapshot("snap1", "E1", ["a"], {}, T0, commit=True)
    eng.create_snapshot("snap1", "E1", ["a"], {}, T0, commit=True)
    assert len(ledger.read_snapshots()) == 1


def test_snapshot_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("snap1", "E1", [], {}, T0, commit=True)
    assert s.snapshot_id == M.snapshot_id("snap1", "E1")


# ── Evolution intelligence / score ──
def test_evolution_score_high():
    assert M.evolution_score(_HI) > 0.7


def test_evolution_score_low():
    assert M.evolution_score(_LO) < 0.4


def test_evolution_score_regression_inverse():
    s = M.evolution_score({"regression_rate": 0.0})
    assert abs(s - 0.20) < 1e-9


def test_evolution_weights_sum_one():
    assert abs(sum(M.EVOLUTION_WEIGHTS.values()) - 1.0) < 1e-9


def test_evolution_health_labels():
    assert M.evolution_health(_HI) == "HEALTHY"
    assert M.evolution_health(_LO) == "DEGRADED"
    assert M.evolution_health({"maturity_growth": 1.0, "capability_expansion": 1.0}) == "WARNING"


def test_trend_label():
    assert M.trend_label(0.1) == M.GROWING
    assert M.trend_label(-0.1) == M.REGRESSING
    assert M.trend_label(0.0) == M.STABLE


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HI)
    assert res["evolution_health"] == "HEALTHY"
    assert res["evolution_score"] > 0.7


def test_capability_evolution_map(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", INITIAL, ["c1"], T0, commit=True)
    eng.create_state("L", DEVELOPING, ["c1", "c2"], T1, commit=True)
    m = eng.capability_evolution_map()
    assert m.get("L") == ["c1", "c2"]  # latest state


def test_structural_change_history(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_event("L", M.E_STRUCTURAL_CHANGE, "reorg", T0, commit=True)
    hist = eng.structural_change_history()
    assert any("structural_change" in h for h in hist)


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.report_id.startswith("GER:")
    assert r.event_count >= 1
    assert r.state_count >= 1
    assert r.assessment_count >= 1


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
    assert M.E_CAPABILITY_ADDED in r.event_type_distribution
    assert DEVELOPING in r.maturity_level_distribution


def test_report_regression_and_capabilities(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", DEVELOPING, ["c1"], T0, commit=True)
    eng.create_state("L", INITIAL, ["c1"], T1, commit=True)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert len(r.regression_indicators) >= 1
    assert "L" in r.capability_evolution_map


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert "EVOLUTION ANALYSIS ≠ EVOLUTION ACTION" in r.disclaimer


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


def test_report_average_maturity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.average_maturity > 0.0


# ── Lineage / verify ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _state(eng)
    anc = eng.trace_lineage(M.artifact_id(M.ART_STATE, s.event_id))
    assert M.artifact_id(M.ART_LAYER, "research_compliance") in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_evolution.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _event(eng)
    p = sp("ge_events.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["description"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_evolution.verify import verify_ledger
    assert verify_ledger(ledger.EVENTS)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _event(eng, desc="d1")
    _event(eng, desc="d2")
    p = sp("ge_events.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_evolution.verify import verify_ledger
    assert verify_ledger(ledger.EVENTS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _event(eng)
    p = sp("ge_events.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_evolution.verify import verify_ledger, duplicate_event_validation
    assert verify_ledger(ledger.EVENTS)["ok"] is False
    assert duplicate_event_validation()["ok"] is False


def test_verify_timeline_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", INITIAL, [], T0, commit=True)
    eng.create_state("L", DEVELOPING, [], T1, commit=True)
    from jarvis.governance_evolution.verify import state_timeline_validation
    assert state_timeline_validation()["ok"] is True


def test_verify_detects_invalid_transition(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", INITIAL, [], T0, commit=True)
    p = sp("ge_states.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["to_maturity"] = "MANAGED"  # from GENESIS ok, but tamper hash? use standalone check
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    # GENESIS->MANAGED is valid (first any); instead craft a skip on a 2nd event
    from jarvis.governance_evolution.verify import state_timeline_validation
    # append a 2nd event skipping levels
    from jarvis.governance_evolution.models import content_hash, state_event_id, state_id
    sid = state_id("L")
    eid = state_event_id(sid, 2)
    rec = {"event_id": eid, "state_id": sid, "layer_reference": "L", "sequence": 2,
           "from_maturity": "MANAGED", "to_maturity": "INITIAL", "maturity_level": "INITIAL",
           "capabilities": [], "regression": True, "timestamp": T1, "created_at": T1,
           "input_hash": "", "record_hash": "", "previous_hash": rows[0]["record_hash"]}
    # from MANAGED(3) to INITIAL(0) delta 3 -> invalid transition
    rec["record_hash"] = content_hash(rec)
    ledger.append_state_event(rec)
    res = state_timeline_validation()
    assert res["ok"] is False
    assert any("invalid_transition" in i for i in res["issues"])


def test_verify_detects_broken_timeline(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", INITIAL, [], T0, commit=True)
    p = sp("ge_states.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["sequence"] = 5  # broken sequence
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_evolution.verify import state_timeline_validation
    res = state_timeline_validation()
    assert res["ok"] is False
    assert any("broken_timeline" in i for i in res["issues"])


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_evolution.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["timeline"]["ok"] is True
    assert res["duplicate"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _event(eng)
    from jarvis.governance_evolution.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "GEA:c1", "artifact_type": "STATE", "ref_id": "x1",
          "parent_artifact": "GEA:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "GEA:c2", "artifact_type": "STATE", "ref_id": "x2",
          "parent_artifact": "GEA:c1", "created_at": T0, "input_hash": "", "record_hash": "",
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
    from jarvis.governance_evolution.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert s.event_count >= 1
    assert s.state_count >= 1
    assert s.assessment_count >= 1
    assert s.pattern_count >= 1
    assert s.comparison_count >= 1
    assert s.snapshot_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


def test_summary_layer_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L1", INITIAL, [], T0, commit=True)
    eng.create_state("L2", INITIAL, [], T0, commit=True)
    assert eng.summary(T0).layer_count == 2


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


def test_upstream_layers_covered_read_only():
    for layer in ("governance_memory", "governance_feedback", "research_compliance"):
        assert layer in ledger.SOURCE_LEDGERS


# ── CLI ──
def test_cli_event(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    rc = main(["event", "--source-layer", "rc", "--event-type", "capability_added",
               "--description", "d", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["event"]["event_id"].startswith("GEE:")


def test_cli_state(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    rc = main(["state", "--layer-reference", "rc", "--maturity-level", "INITIAL",
               "--capabilities", "c1,c2", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["state"]["state_id"].startswith("GSX:")


def test_cli_maturity(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    rc = main(["maturity", "--layer-reference", "rc", "--scores-json", json.dumps(_DIMS),
               "--epoch", "E1", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["maturity"]["assessment_id"].startswith("GEM:")


def test_cli_pattern(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    rc = main(["pattern", "--sequence", "capability_added,maturity_shift", "--frequency", "2",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["pattern"]["pattern_id"].startswith("GEP:")


def test_cli_compare(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    main(["state", "--layer-reference", "L", "--maturity-level", "INITIAL", "--commit"])
    s1 = json.loads(capsys.readouterr().out)["state"]["event_id"]
    main(["state", "--layer-reference", "L", "--maturity-level", "DEVELOPING", "--commit"])
    s2 = json.loads(capsys.readouterr().out)["state"]["event_id"]
    rc = main(["compare", "--previous-state", s1, "--current-state", s2, "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["comparison"]["comparison_id"].startswith("GEC:")


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    rc = main(["snapshot", "--name", "s1", "--epoch", "E1", "--states", "a,b", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["snapshot"]["snapshot_id"].startswith("GEN:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    rc = main(["report", "--metrics-json", json.dumps(_HI), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("GER:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    main(["event", "--source-layer", "rc", "--event-type", "capability_added", "--description",
          "d", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    main(["event", "--source-layer", "rc", "--event-type", "capability_added", "--description",
          "d", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_evolution.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "event_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.governance_evolution.engine as eng_mod
    import jarvis.governance_evolution.models as mdl_mod
    import jarvis.governance_evolution.ledger as led_mod
    import jarvis.governance_evolution.verify as ver_mod
    import jarvis.governance_evolution.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "modify_policy(", "change_permission(", "auto_upgrade(",
                 "auto_migrate("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.governance_evolution.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def deploy", "def trade", "def place_order",
               "def allocate_capital", "def modify_policy", "def change_permission",
               "def auto_upgrade", "def auto_migrate"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(GovernanceEvolutionEngine))
    for banned in ("execute", "deploy", "trade", "place_order", "allocate_capital",
                   "modify_policy", "change_permission", "auto_upgrade", "auto_migrate"):
        assert banned not in api


def test_analysis_not_action(tmp_path, monkeypatch):
    """상태 레코드에 apply/upgrade/execute/migrate 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    s = _state(_eng())
    d = s.to_dict()
    for banned in ("apply", "upgrade", "execute", "migrate", "deploy"):
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
        m = importlib.import_module(f"jarvis.governance_evolution.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_ge(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("ge_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 8


def test_engine_no_upstream_layer_import():
    import jarvis.governance_evolution.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.governance_memory", "import jarvis.governance_feedback",
               "import jarvis.research_evolution", "import jarvis.meta_intelligence"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.event_id("a", "b", "c")[:4],
        M.state_id("a")[:4],
        M.state_event_id("a", 1)[:4],
        M.maturity_id("a", "b")[:4],
        M.pattern_id(["a"])[:4],
        M.comparison_id("a", "b")[:4],
        M.snapshot_id("a", "b")[:4],
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


def test_snapshot_hash_sorts_states():
    assert M.snapshot_hash(["b", "a"], {}) == M.snapshot_hash(["a", "b"], {})


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_event_types_count():
    assert len(M.EVENT_TYPES) == 6


def test_maturity_levels_count():
    assert len(M.MATURITY_LEVELS) == 5


def test_maturity_dimensions_count():
    assert len(M.MATURITY_DIMENSIONS) == 6


def test_node_types_count():
    assert len(M.NODE_TYPES) == 6


def test_pattern_confidence_bounds():
    assert M.pattern_confidence(100, 100) == 1.0
    assert M.pattern_confidence(-5, -5) == 0.0


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _event(eng, commit=False)
    _state(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_event_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _event(_eng())
    d = e.to_dict()
    assert d["event_id"] == e.event_id
    assert set(("source_layer", "event_type", "description")).issubset(d)


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


def test_event_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _event(_eng())
    assert e.input_hash == M.input_digest("research_compliance", M.E_CAPABILITY_ADDED,
                                          "added OOS gate")


def test_maturity_dimension_scores_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().assess_maturity("L", _DIMS, "", "E1", T0, commit=True)
    assert m.dimension_scores == _DIMS


def test_snapshot_summary_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("s1", "E1", ["a"], {"layers": 3}, T0, commit=True)
    assert s.summary == {"layers": 3}


def test_summary_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert M.E_CAPABILITY_ADDED in s.event_type_distribution
    assert DEVELOPING in s.maturity_level_distribution


def test_regression_indicators_empty_when_growing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_state("L", INITIAL, [], T0, commit=True)
    eng.create_state("L", DEVELOPING, [], T1, commit=True)
    assert eng.regression_indicators() == []


def test_source_ledgers_not_ge_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("ge_")
        assert isinstance(idf, str)


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e1 = _event(eng, desc="d1")
    e2 = _event(eng, desc="d2")
    assert e1.event_id != e2.event_id
    assert len(ledger.read_events()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    for phrase in ("EVOLUTION ANALYSIS ≠ EVOLUTION ACTION", "MATURITY SCORE ≠ PERMISSION",
                   "TREND DETECTION ≠ CHANGE EXECUTION", "RECOMMENDATION ≠ IMPLEMENTATION"):
        assert phrase in r.disclaimer


def test_evolution_score_partial_metrics():
    s = M.evolution_score({"maturity_growth": 1.0, "change_stability": 1.0})
    assert abs(s - (0.30 + 0.20)) < 1e-9


def test_maturity_trajectory_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().maturity_trajectory("none") == []
