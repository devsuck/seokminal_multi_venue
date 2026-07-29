"""P10.25 Research Risk Intelligence 테스트. **연구 과정 리스크 분석(투자 실행 리스크 아님) 전용.**

리스크 레지스트리(생명주기 UNKNOWN→ANALYZING→ASSESSED→REVIEWED)·리스크 요인(불변·범주)·리스크 평가(결정적
점수·불변·PASS/WARNING/CRITICAL)·리스크 리포트(overall·결정적)·verify(체인/변조/중복/전이/계보)·replay·상위
READ ONLY 보호·CLI·보안(금지import·한도변경/자본결정/전략거부/배포 없음·상위 원장 무변경·삭제 API 없음·불변·
RISK ANALYSIS≠RISK LIMIT CHANGE·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_risk_intelligence import ledger
from jarvis.research_risk_intelligence import models as M
from jarvis.research_risk_intelligence.engine import ResearchRiskIntelligenceEngine
from jarvis.research_risk_intelligence.models import (
    ANALYZING,
    ASSESSED,
    CRITICAL,
    PASS,
    REVIEWED,
    UNKNOWN,
    WARNING,
    IllegalTransition,
    ImmutableAssessmentError,
    ImmutableFactorError,
    InvalidRiskCategory,
    UnknownRisk,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

# 낮은 리스크(PASS) / 높은 리스크(CRITICAL) dimension_scores
_LOWRISK = {"overfitting_risk": 0.1, "data_leakage_risk": 0.1, "false_discovery_risk": 0.1,
            "complexity_risk": 0.1, "validation_weakness": 0.1, "reproducibility_risk": 0.1}
_HIGHRISK = {"overfitting_risk": 0.9, "data_leakage_risk": 0.9, "false_discovery_risk": 0.9,
             "complexity_risk": 0.9, "validation_weakness": 0.9, "reproducibility_risk": 0.9}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_risk_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchRiskIntelligenceEngine()


def _risk(eng, layer="strategy_governance", ref="rg:ST1", cat=None, commit=True):
    return eng.register_risk(layer, ref, cat or M.R_OVERFITTING, T0, commit=commit)


def _full(eng):
    """risk→factor→assess→review→report end-to-end."""
    r = _risk(eng)
    eng.record_factor(r.risk_id, "is_oos_gap", M.R_OVERFITTING, 0.8, 1.0, "large gap", T0,
                      commit=True)
    eng.assess_risk(r.risk_id, _HIGHRISK, "ev1", "E1", T0, commit=True)
    eng.review_risk(r.risk_id, T1, commit=True)
    eng.generate_report("GLOBAL", {}, T2, commit=True)
    return r


# ── Risk Registry ──
def test_risk_register(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _risk(_eng())
    assert r.risk_id.startswith("RRK:")
    assert r.to_state == UNKNOWN
    assert r.risk_category == M.R_OVERFITTING


def test_risk_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidRiskCategory):
        _eng().register_risk("L", "ref", "not_a_risk", T0, commit=True)


def test_risk_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, cat in enumerate(M.RISK_CATEGORIES):
        r = eng.register_risk("L", f"ref{i}", cat, T0, commit=True)
        assert r.risk_category == cat
    assert len(ledger.distinct_risks()) == len(M.RISK_CATEGORIES)


def test_risk_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _risk(eng)
    b = _risk(eng)
    assert a.risk_id == b.risk_id
    assert len(ledger.distinct_risks()) == 1


def test_risk_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _risk(_eng())
    assert r.risk_id == M.risk_id("rg:ST1", M.R_OVERFITTING)


def test_risk_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _risk(_eng(), commit=False)
    assert ledger.read_risk_events() == []


def test_risk_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.transition_risk(r.risk_id, ANALYZING, T1, commit=True)
    eng.transition_risk(r.risk_id, ASSESSED, T1, commit=True)
    eng.transition_risk(r.risk_id, REVIEWED, T2, commit=True)
    assert eng.risk_state(r.risk_id) == REVIEWED


def test_risk_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_risk(r.risk_id, ASSESSED, T1, commit=True)  # skips ANALYZING


def test_risk_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRisk):
        _eng().transition_risk("RRK:nope", ANALYZING, T1, commit=True)


def test_risk_reviewed_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.transition_risk(r.risk_id, ANALYZING, T1, commit=True)
    eng.transition_risk(r.risk_id, ASSESSED, T1, commit=True)
    eng.transition_risk(r.risk_id, REVIEWED, T2, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_risk(r.risk_id, ANALYZING, T2, commit=True)


def test_risk_can_transition_table():
    assert M.can_transition_risk("", UNKNOWN)
    assert M.can_transition_risk(UNKNOWN, ANALYZING)
    assert M.can_transition_risk(ANALYZING, ASSESSED)
    assert M.can_transition_risk(ASSESSED, REVIEWED)
    assert not M.can_transition_risk(UNKNOWN, ASSESSED)
    assert not M.can_transition_risk(REVIEWED, UNKNOWN)


def test_risk_records_layer_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _risk(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_LAYER, "strategy_governance"))
    ra = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == r.risk_id and a["artifact_type"] == M.ART_RISK)
    assert ra["parent_artifact"] == M.artifact_id(M.ART_LAYER, "strategy_governance")


# ── Risk Factor ──
def test_factor_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    f = eng.record_factor(r.risk_id, "is_oos_gap", M.R_OVERFITTING, 0.8, 1.0, "gap", T0,
                          commit=True)
    assert f.factor_id.startswith("RRF:")
    assert f.value == 0.8


def test_factor_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidRiskCategory):
        _eng().record_factor("RRK:x", "f", "not_a_cat", 0.5, 1.0, "", T0, commit=True)


def test_factor_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_factor("RRK:x", "f1", M.R_OVERFITTING, 0.5, 1.0, "", T0, commit=True)
    with pytest.raises(ImmutableFactorError):
        eng.record_factor("RRK:x", "f1", M.R_OVERFITTING, 0.9, 1.0, "", T0, commit=True)


def test_factor_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.record_factor("RRK:x", "f1", M.R_OVERFITTING, 0.5, 1.0, "", T0, commit=True)
    b = eng.record_factor("RRK:x", "f1", M.R_OVERFITTING, 0.5, 1.0, "", T0, commit=True)
    assert a.factor_id == b.factor_id
    assert len(ledger.read_factors()) == 1


def test_factor_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _eng().record_factor("RRK:x", "f1", M.R_OVERFITTING, 0.5, 1.0, "", T0, commit=True)
    assert f.factor_id == M.factor_id("RRK:x", "f1")


def test_factor_parent_links_risk(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    f = eng.record_factor(r.risk_id, "f1", M.R_OVERFITTING, 0.5, 1.0, "", T0, commit=True)
    fa = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == f.factor_id and a["artifact_type"] == M.ART_FACTOR)
    assert fa["parent_artifact"] == M.artifact_id(M.ART_RISK, r.risk_id)


def test_factors_for(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_factor("RRK:x", "f1", M.R_OVERFITTING, 0.5, 1.0, "", T0, commit=True)
    eng.record_factor("RRK:x", "f2", M.R_COMPLEXITY, 0.6, 1.0, "", T0, commit=True)
    assert len(ledger.factors_for("RRK:x")) == 2


# ── Risk Assessment (deterministic score) ──
def test_assess_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    a = eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    assert a.assessment_id.startswith("RRA:")
    assert a.risk_label == CRITICAL


def test_assess_low_risk_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    a = eng.assess_risk(r.risk_id, _LOWRISK, "ev", "E1", T0, commit=True)
    assert a.risk_label == PASS
    assert a.risk_score < 0.4


def test_assess_advances_risk(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    assert eng.risk_state(r.risk_id) == ASSESSED


def test_assess_deterministic_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    a = eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    assert a.risk_score == M.risk_score(_HIGHRISK)


def test_assess_from_factors(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.record_factor(r.risk_id, "f1", M.R_OVERFITTING, 0.9, 1.0, "", T0, commit=True)
    eng.record_factor(r.risk_id, "f2", M.R_DATA_LEAKAGE, 0.8, 1.0, "", T0, commit=True)
    a = eng.assess_risk(r.risk_id, None, "ev", "E1", T0, commit=True)  # aggregate from factors
    assert a.dimension_scores.get(M.R_OVERFITTING) == 0.9
    assert a.dimension_scores.get(M.R_DATA_LEAKAGE) == 0.8


def test_assess_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    with pytest.raises(ImmutableAssessmentError):
        eng.assess_risk(r.risk_id, _LOWRISK, "ev", "E1", T0, commit=True)


def test_assess_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    a = eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    b = eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    assert a.assessment_id == b.assessment_id
    assert len(ledger.read_assessments()) == 1


def test_assess_unknown_risk(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRisk):
        _eng().assess_risk("RRK:nope", _HIGHRISK, "ev", "E1", T0, commit=True)


def test_assess_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    a = eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    assert a.assessment_id == M.assessment_id(r.risk_id, "E1")


def test_assess_parent_links_risk(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    a = eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    aa = next(x for x in ledger.read_artifacts()
              if x["ref_id"] == a.assessment_id and x["artifact_type"] == M.ART_ASSESSMENT)
    assert aa["parent_artifact"] == M.artifact_id(M.ART_RISK, r.risk_id)


# ── review ──
def test_review_risk(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    res = eng.review_risk(r.risk_id, T1, commit=True)
    assert eng.risk_state(r.risk_id) == REVIEWED
    assert "거부" in res["note"]


def test_review_requires_assessed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    with pytest.raises(IllegalTransition):
        eng.review_risk(r.risk_id, T1, commit=True)  # still UNKNOWN


def test_review_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRisk):
        _eng().review_risk("RRK:nope", T1, commit=True)


# ── score / label helpers ──
def test_risk_score_high():
    assert M.risk_score(_HIGHRISK) > 0.7


def test_risk_score_low():
    assert M.risk_score(_LOWRISK) < 0.4


def test_risk_weights_sum_one():
    assert abs(sum(M.RISK_WEIGHTS.values()) - 1.0) < 1e-9


def test_risk_label_levels():
    assert M.risk_label(_HIGHRISK) == CRITICAL
    assert M.risk_label(_LOWRISK) == PASS
    assert M.risk_label({"overfitting_risk": 1.0, "data_leakage_risk": 1.0}) == WARNING


def test_label_from_score():
    assert M.label_from_score(0.9) == CRITICAL
    assert M.label_from_score(0.5) == WARNING
    assert M.label_from_score(0.1) == PASS


def test_worst_label():
    assert M.worst_label([PASS, WARNING, CRITICAL]) == CRITICAL
    assert M.worst_label([PASS, WARNING]) == WARNING
    assert M.worst_label([]) == PASS


def test_aggregate_factors():
    factors = [{"category": M.R_OVERFITTING, "value": 0.8, "weight": 1.0},
               {"category": M.R_OVERFITTING, "value": 0.6, "weight": 1.0},
               {"category": M.R_COMPLEXITY, "value": 0.4, "weight": 2.0}]
    agg = M.aggregate_factors(factors)
    assert abs(agg[M.R_OVERFITTING] - 0.7) < 1e-9
    assert abs(agg[M.R_COMPLEXITY] - 0.4) < 1e-9


def test_aggregate_factors_ignores_unknown():
    assert M.aggregate_factors([{"category": "nope", "value": 1.0}]) == {}


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HIGHRISK)
    assert res["risk_label"] == CRITICAL
    assert res["risk_score"] > 0.7


def test_risk_score_empty_zero():
    assert M.risk_score({}) == 0.0


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", {}, T2, commit=True)
    assert r.report_id.startswith("RRP:")
    assert r.risk_count >= 1
    assert r.assessment_count >= 1
    assert r.overall_label == CRITICAL


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    a = eng.generate_report("GLOBAL", {}, T2, commit=False)
    b = eng.generate_report("GLOBAL", {}, T2, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", {}, T2, commit=True)
    assert M.R_OVERFITTING in r.risk_category_distribution
    assert CRITICAL in r.assessment_label_distribution


def test_report_high_risk_items(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    rep = eng.generate_report("GLOBAL", {}, T1, commit=True)
    assert r.risk_id in rep.high_risk_items


def test_report_average_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", {}, T2, commit=True)
    assert r.average_risk_score > 0.7


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    assert "RISK ANALYSIS ≠ RISK LIMIT CHANGE" in r.disclaimer


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("GLOBAL", {}, T0, commit=True)
    eng.generate_report("GLOBAL", {}, T0, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_no_decision_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    d = r.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d, ensure_ascii=False).lower()
    for verb in ("reject", "deploy", "allocate_capital", "place_order", "risk_limit"):
        assert verb not in blob


# ── Lineage / verify ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    a = eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    anc = eng.trace_lineage(M.artifact_id(M.ART_ASSESSMENT, a.assessment_id))
    assert M.artifact_id(M.ART_RISK, r.risk_id) in anc
    assert M.artifact_id(M.ART_LAYER, "strategy_governance") in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_risk_intelligence.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_risk_intelligence.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    p = sp("rr_assessments.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["risk_score"] = 0.0
    with open(p, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    from jarvis.research_risk_intelligence.verify import verify_ledger
    assert verify_ledger(ledger.ASSESSMENTS)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_factor("RRK:x", "f1", M.R_OVERFITTING, 0.5, 1.0, "", T0, commit=True)
    eng.record_factor("RRK:x", "f2", M.R_COMPLEXITY, 0.6, 1.0, "", T0, commit=True)
    p = sp("rr_factors.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    from jarvis.research_risk_intelligence.verify import verify_ledger
    assert verify_ledger(ledger.FACTORS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_factor("RRK:x", "f1", M.R_OVERFITTING, 0.5, 1.0, "", T0, commit=True)
    p = sp("rr_factors.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))
    with open(p, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    from jarvis.research_risk_intelligence.verify import verify_ledger
    assert verify_ledger(ledger.FACTORS)["ok"] is False


def test_verify_risk_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    from jarvis.research_risk_intelligence.verify import risk_transition_validation
    assert risk_transition_validation()["ok"] is True


def test_verify_detects_bad_transition(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _risk(eng)
    p = sp("rr_risks.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["to_state"] = "ASSESSED"  # illegal from GENESIS
    with open(p, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    from jarvis.research_risk_intelligence.verify import risk_transition_validation
    assert risk_transition_validation()["ok"] is False


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_risk_intelligence.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["risk_transitions"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _risk(eng)
    from jarvis.research_risk_intelligence.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "RRX:c1", "artifact_type": "RISK", "ref_id": "x1",
          "parent_artifact": "RRX:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "RRX:c2", "artifact_type": "RISK", "ref_id": "x2",
          "parent_artifact": "RRX:c1", "created_at": T0, "input_hash": "", "record_hash": "",
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
    from jarvis.research_risk_intelligence.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert s.risk_count >= 1
    assert s.factor_count >= 1
    assert s.assessment_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


def test_summary_state_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert REVIEWED in s.risk_state_distribution
    assert CRITICAL in s.assessment_label_distribution


def test_assessed_label(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    assert eng.assessed_label(r.risk_id) == CRITICAL
    assert eng.assessed_label("RRK:none") == PASS


# ── 상위 READ ONLY ──
def test_list_source_objects_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("strategy_governance") == []


def test_list_source_objects_reads(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rg_strategies.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
        f.write(json.dumps({"strategy_id": "ST2"}) + "\n")
    out = _eng().list_source_objects("strategy_governance")
    assert out == ["strategy_governance:ST1", "strategy_governance:ST2"]


def test_source_read_only_no_write(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    src = sp("rg_strategies.jsonl")
    with open(src, "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
    before = open(src).read()
    eng = _eng()
    _full(eng)
    eng.list_source_objects("strategy_governance")
    assert open(src).read() == before


def test_unknown_source_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("nonexistent") == []


def test_source_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("ai_signals.jsonl"), "w") as f:
        f.write(json.dumps({"signal_id": "S1"}) + "\n")
    assert ledger.source_count("alpha_intelligence") == 1
    assert ledger.source_count("nope") == 0


def test_source_layers_are_the_five():
    assert set(ledger.SOURCE_LEDGERS) == {"strategy_governance", "alpha_intelligence",
                                          "portfolio_research", "decision_intelligence",
                                          "simulation_environment"}


# ── CLI ──
def test_cli_risk(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_risk_intelligence.__main__ import main
    rc = main(["risk", "--source-layer", "strategy_governance", "--source-reference", "rg:ST1",
               "--category", "overfitting_risk", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["risk"]["risk_id"].startswith("RRK:")


def test_cli_factor(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_risk_intelligence.__main__ import main
    rc = main(["factor", "--risk-ref", "RRK:x", "--name", "f1", "--category", "overfitting_risk",
               "--value", "0.8", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["factor"]["factor_id"].startswith("RRF:")


def test_cli_assess(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_risk_intelligence.__main__ import main
    main(["risk", "--source-layer", "L", "--source-reference", "r1", "--category",
          "overfitting_risk", "--commit"])
    rid = json.loads(capsys.readouterr().out)["risk"]["risk_id"]
    rc = main(["assess", "--risk-ref", rid, "--scores-json", json.dumps(_HIGHRISK), "--epoch",
               "E1", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["assessment"]["risk_label"] == "CRITICAL"


def test_cli_review(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_risk_intelligence.__main__ import main
    main(["risk", "--source-layer", "L", "--source-reference", "r1", "--category",
          "overfitting_risk", "--commit"])
    rid = json.loads(capsys.readouterr().out)["risk"]["risk_id"]
    main(["assess", "--risk-ref", rid, "--scores-json", json.dumps(_HIGHRISK), "--epoch", "E1",
          "--commit"])
    capsys.readouterr()
    rc = main(["review", "--risk-ref", rid, "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["review"]["state"] == "REVIEWED"


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_risk_intelligence.__main__ import main
    rc = main(["report", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("RRP:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_risk_intelligence.__main__ import main
    main(["risk", "--source-layer", "L", "--source-reference", "r1", "--category",
          "complexity_risk", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_risk_intelligence.__main__ import main
    main(["risk", "--source-layer", "L", "--source-reference", "r1", "--category",
          "complexity_risk", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_risk_intelligence.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "risk_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_risk_intelligence.engine as eng_mod
    import jarvis.research_risk_intelligence.models as mdl_mod
    import jarvis.research_risk_intelligence.ledger as led_mod
    import jarvis.research_risk_intelligence.verify as ver_mod
    import jarvis.research_risk_intelligence.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "reject_strategy(", "change_risk_limit("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_decision_methods():
    import jarvis.research_risk_intelligence.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def change_risk_limit", "def allocate_capital", "def reject_strategy",
               "def deploy", "def execute", "def trade", "def approve", "def reject"):
        assert kw not in src


def test_no_decision_authority_api():
    api = set(dir(ResearchRiskIntelligenceEngine))
    for banned in ("change_risk_limit", "allocate_capital", "reject_strategy", "deploy",
                   "execute", "trade", "approve", "reject", "place_order"):
        assert banned not in api


def test_assessment_not_decision(tmp_path, monkeypatch):
    """평가 레코드에 reject/approve/deploy/allocate 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    a = eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    d = a.to_dict()
    for banned in ("reject", "approve", "deploy", "allocate", "limit"):
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
        m = importlib.import_module(f"jarvis.research_risk_intelligence.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_rr(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("rr_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 5


def test_engine_no_upstream_layer_import():
    import jarvis.research_risk_intelligence.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.research_governance", "import jarvis.alpha_intelligence",
               "import jarvis.decision_intelligence", "import jarvis.simulation_environment"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.risk_id("a", "b")[:4],
        M.risk_event_id("a", "", UNKNOWN)[:4],
        M.factor_id("a", "b")[:4],
        M.assessment_id("a", "b")[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 6


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_risk_categories_count():
    assert len(M.RISK_CATEGORIES) == 6


def test_risk_states_count():
    assert len(M.RISK_STATES) == 4


def test_results_count():
    assert len(M.RESULTS) == 3


def test_node_types_count():
    assert len(M.NODE_TYPES) == 5


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _risk(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_risk_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _risk(_eng())
    d = r.to_dict()
    assert d["risk_id"] == r.risk_id
    assert set(("source_layer", "source_reference", "risk_category")).issubset(d)


def test_report_metrics_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {"k": 1}, T0, commit=True)
    assert r.metrics == {"k": 1}


def test_multiple_scopes_distinct_reports(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("A", {}, T0, commit=True)
    eng.generate_report("B", {}, T0, commit=True)
    assert len(ledger.read_reports()) == 2


def test_risk_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _risk(_eng())
    assert r.input_hash == M.input_digest(r.risk_id, "", UNKNOWN)


def test_factor_weight_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _eng().record_factor("RRK:x", "f1", M.R_COMPLEXITY, 0.5, 2.5, "", T0, commit=True)
    assert f.weight == 2.5


def test_assessment_dimension_scores_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _risk(eng)
    a = eng.assess_risk(r.risk_id, _HIGHRISK, "ev", "E1", T0, commit=True)
    assert a.dimension_scores == _HIGHRISK


def test_high_risk_items_threshold(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r1 = eng.register_risk("L", "r1", M.R_OVERFITTING, T0, commit=True)
    r2 = eng.register_risk("L", "r2", M.R_COMPLEXITY, T0, commit=True)
    eng.assess_risk(r1.risk_id, _HIGHRISK, "", "E1", T0, commit=True)
    eng.assess_risk(r2.risk_id, _LOWRISK, "", "E1", T0, commit=True)
    assert eng.high_risk_items() == [r1.risk_id]


def test_source_ledgers_not_rr_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("rr_")
        assert isinstance(idf, str)


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.register_risk("L", "r1", M.R_OVERFITTING, T0, commit=True)
    b = eng.register_risk("L", "r2", M.R_COMPLEXITY, T0, commit=True)
    assert a.risk_id != b.risk_id
    assert len(ledger.distinct_risks()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    for phrase in ("RISK ANALYSIS ≠ RISK LIMIT CHANGE", "ASSESSMENT ≠ CAPITAL DECISION",
                   "FINDING ≠ STRATEGY REJECTION", "SCORE ≠ DEPLOYMENT DECISION"):
        assert phrase in r.disclaimer


def test_disclaimer_not_investment_risk(tmp_path, monkeypatch):
    """디스클레이머가 '투자 실행 리스크 아님 — 연구 과정 리스크만'을 명시."""
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    assert "연구 과정 리스크" in r.disclaimer


def test_risk_score_partial_dims():
    s = M.risk_score({"overfitting_risk": 1.0, "data_leakage_risk": 1.0})
    assert abs(s - (0.25 + 0.20)) < 1e-9
