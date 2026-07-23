"""P10.12 Research Meta Intelligence 테스트. **연구 과정 메타 분석 전용.**

패턴(불변)·생명주기(DISCOVERED→ANALYZED→CONFIRMED→ARCHIVED, 차단전이)·방법·결과(RECORDED→REVIEWED→
CLASSIFIED, 결과유형)·실패 패턴·품질 점수(0~100)·인사이트(GENERATED→REVIEWED→ARCHIVED, HIGH/MEDIUM/
LOW)·진화 그래프(노드/엣지 검증·순환)·메타 리포트·verify(체인/변조/중복/계보/순환)·replay·상위 READ
ONLY 보호·CLI·보안(금지import·실행/거래/배포/선택/자본배분 없음·상위 원장 무변경·삭제 API 없음·불변·
META SCORE≠TRADING SCORE·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.meta_intelligence import ledger
from jarvis.meta_intelligence import models as M
from jarvis.meta_intelligence.engine import ResearchMetaEngine
from jarvis.meta_intelligence.models import (
    ANALYZED,
    ARCHIVED,
    CLASSIFIED,
    CONFIRMED,
    DISCOVERED,
    FAILED,
    GENERATED,
    HIGH_CONFIDENCE,
    INCONCLUSIVE,
    LOW_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    RECORDED,
    REVIEWED,
    SUCCESS,
    WARNING,
    IllegalTransition,
    ImmutableFailureError,
    ImmutableMethodError,
    ImmutablePatternError,
    InvalidEvolutionLink,
    UnknownInsight,
    UnknownOutcome,
    UnknownPattern,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_QUAL = {"reproducibility": 0.9, "validation_depth": 0.8, "data_quality": 0.85,
         "robustness": 0.8, "lineage_completeness": 0.9, "evidence_strength": 0.85}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.meta_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchMetaEngine()


# ── Pattern ──
def test_register_pattern(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.register_pattern(M.OVERFITTING, "repeated overfit", 3, ["rg:ST1"], 0.7, T0,
                             commit=True)
    assert p.status == DISCOVERED and p.frequency == 3


def test_pattern_id_deterministic():
    a = M.pattern_id("c", "d")
    assert a == M.pattern_id("c", "d") and a.startswith("MIP:")


def test_pattern_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_pattern("c", "d", 1, [], 0.5, T0, commit=True)
    assert len(ledger.read_pattern_events()) == 1


def test_pattern_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_pattern("c", "d", 1, [], 0.5, T0, commit=False)
    assert ledger.read_pattern_events() == []


def test_pattern_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_pattern("c", "d", 1, [], 0.5, T0, commit=True)
    with pytest.raises(ImmutablePatternError):
        eng.register_pattern("c", "d", 9, [], 0.5, T0, commit=True)


def test_pattern_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_pattern("c", "d", 1, [], 0.5, T0, commit=True)
    eng.register_pattern("c", "d", 1, [], 0.5, T0, commit=True)
    assert len(ledger.distinct_patterns()) == 1


def test_pattern_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.register_pattern("c", "d", 1, [], 0.5, T0, commit=True)
    pid = p.pattern_id
    eng.transition_pattern(pid, ANALYZED, T1, commit=True)
    eng.transition_pattern(pid, CONFIRMED, T1, commit=True)
    eng.transition_pattern(pid, ARCHIVED, T2, commit=True)
    assert eng.pattern_state(pid) == ARCHIVED


def test_pattern_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.register_pattern("c", "d", 1, [], 0.5, T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_pattern(p.pattern_id, CONFIRMED, T1, commit=True)


def test_pattern_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.register_pattern("c", "d", 1, [], 0.5, T0, commit=True)
    for to in (ANALYZED, CONFIRMED, ARCHIVED):
        eng.transition_pattern(p.pattern_id, to, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_pattern(p.pattern_id, DISCOVERED, T2, commit=True)


def test_pattern_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPattern):
        _eng().transition_pattern("GHOST", ANALYZED, T1, commit=True)


def test_pattern_transition_table():
    assert M.can_transition_pattern("", DISCOVERED)
    assert M.can_transition_pattern(DISCOVERED, ANALYZED)
    assert M.can_transition_pattern(ANALYZED, CONFIRMED)
    assert not M.can_transition_pattern(DISCOVERED, CONFIRMED)


# ── Method ──
def test_register_method(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = eng.register_method(M.WALK_FORWARD_VALIDATION, "1.0", "validation", 0, 0.0, {}, T0,
                            commit=True)
    assert m.name == M.WALK_FORWARD_VALIDATION
    assert len(ledger.read_methods()) == 1


def test_method_id_deterministic():
    assert M.method_id("n", "1").startswith("MIM:")


def test_method_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_method("m", "1", "", 0, 0.0, {"a": 1}, T0, commit=True)
    with pytest.raises(ImmutableMethodError):
        eng.register_method("m", "1", "", 0, 0.0, {"a": 2}, T0, commit=True)


def test_method_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_method("m", "1", "", 0, 0.0, {}, T0, commit=True)
    eng.register_method("m", "1", "", 0, 0.0, {}, T0, commit=True)
    assert len(ledger.read_methods()) == 1


@pytest.mark.parametrize("name", list(M.RESEARCH_METHODS))
def test_method_examples(tmp_path, monkeypatch, name):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = eng.register_method(name, "1", "", 0, 0.0, {}, T0, commit=True)
    assert m.name == name


def test_method_effectiveness(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = eng.register_method("wf", "1", "", 0, 0.0, {}, T0, commit=True)
    eng.record_outcome("rg", "ST1", SUCCESS, {}, "", m.method_id, T0, commit=True)
    eng.record_outcome("rg", "ST2", FAILED, {}, "", m.method_id, T0, commit=True)
    eff = eng.method_effectiveness(m.method_id)
    assert eff["usage_count"] == 2 and eff["success_rate"] == 0.5


# ── Outcome ──
def test_record_outcome(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = eng.record_outcome("research_governance", "ST1", SUCCESS, {"sharpe": 1.2}, "rv:V1", "",
                           T0, commit=True)
    assert o.result_type == SUCCESS and o.status == RECORDED


@pytest.mark.parametrize("rt", list(M.RESULT_TYPES))
def test_outcome_result_types(tmp_path, monkeypatch, rt):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = eng.record_outcome("rg", f"O_{rt}", rt, {}, "", "", T0, commit=True)
    assert o.result_type == rt


def test_outcome_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_outcome("rg", "ST1", SUCCESS, {}, "", "", T0, commit=True)
    eng.record_outcome("rg", "ST1", SUCCESS, {}, "", "", T0, commit=True)
    assert len(ledger.distinct_outcomes()) == 1


def test_outcome_classify(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = eng.record_outcome("rg", "ST1", SUCCESS, {}, "", "", T0, commit=True)
    eng.classify_outcome(o.outcome_id, T1, commit=True)
    assert eng.outcome_state(o.outcome_id) == CLASSIFIED


def test_outcome_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = eng.record_outcome("rg", "ST1", SUCCESS, {}, "", "", T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_outcome(o.outcome_id, CLASSIFIED, T1, commit=True)


def test_outcome_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownOutcome):
        _eng().transition_outcome("GHOST", REVIEWED, T1, commit=True)


def test_outcome_transition_table():
    assert M.can_transition_outcome("", RECORDED)
    assert M.can_transition_outcome(RECORDED, REVIEWED)
    assert M.can_transition_outcome(REVIEWED, CLASSIFIED)
    assert not M.can_transition_outcome(RECORDED, CLASSIFIED)


def test_outcome_no_automatic_judgment(tmp_path, monkeypatch):
    """결과 레코드에 자동 판단/추천 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = eng.record_outcome("rg", "ST1", SUCCESS, {}, "", "", T0, commit=True)
    for banned in ("recommendation", "action", "decision", "deploy"):
        assert banned not in o.to_dict()


def test_outcome_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = eng.record_outcome("rg", "ST1", SUCCESS, {}, "", "", T0, commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    oa = arts[M.artifact_id(M.ART_OUTCOME, o.outcome_id)]
    assert oa["parent_artifact"] in arts  # SOURCE 부모 존재


# ── Failure ──
def test_record_failure(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    f = eng.record_failure(M.OVERFITTING, 5, ["ST1", "ST2"], 0.8, T0, commit=True)
    assert f.category == M.OVERFITTING and f.occurrences == 5
    assert len(ledger.read_failures()) == 1


@pytest.mark.parametrize("cat", list(M.FAILURE_CATEGORIES))
def test_failure_categories(tmp_path, monkeypatch, cat):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    f = eng.record_failure(cat, 1, [], 0.5, T0, commit=True)
    assert f.category == cat


def test_failure_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_failure("overfitting", 1, ["a"], 0.5, T0, commit=True)
    with pytest.raises(ImmutableFailureError):
        eng.record_failure("overfitting", 9, ["a"], 0.5, T0, commit=True)


def test_failure_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_failure("overfitting", 1, [], 0.5, T0, commit=True)
    eng.record_failure("overfitting", 1, [], 0.5, T0, commit=True)
    assert len(ledger.read_failures()) == 1


# ── Quality ──
def test_compute_quality_full():
    comps = {k: 1.0 for k in M.QUALITY_WEIGHTS}
    assert abs(M.compute_quality(comps) - 100.0) < 1e-6


def test_compute_quality_weighted():
    comps = {k: 0.0 for k in M.QUALITY_WEIGHTS}
    comps["reproducibility"] = 1.0
    assert abs(M.compute_quality(comps) - 20.0) < 1e-6


def test_quality_weights_sum_one():
    assert abs(sum(M.QUALITY_WEIGHTS.values()) - 1.0) < 1e-9


def test_quality_grade_boundaries():
    assert M.quality_grade(90) == "A"
    assert M.quality_grade(75) == "B"
    assert M.quality_grade(55) == "C"
    assert M.quality_grade(40) == "D"


def test_calculate_quality(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    q = eng.calculate_quality("ST1", _QUAL, T0, commit=True)
    assert 0 <= q.overall_score <= 100 and q.grade in ("A", "B", "C", "D")
    assert len(ledger.read_quality_scores()) == 1


def test_calculate_quality_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.calculate_quality("ST1", _QUAL, T0, commit=True)
    eng.calculate_quality("ST1", _QUAL, T0, commit=True)
    assert len(ledger.read_quality_scores()) == 1


def test_quality_not_strategy_ranking(tmp_path, monkeypatch):
    """품질 레코드에 ranking/performance/selection 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    q = eng.calculate_quality("ST1", _QUAL, T0, commit=True)
    for banned in ("ranking", "performance", "selected", "deploy"):
        assert banned not in q.to_dict()


# ── Insight ──
def test_generate_insight(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = {"research_reliability": 0.9, "validation_consistency": 0.85, "method_effectiveness": 0.8,
         "evidence_completeness": 0.8, "failure_recurrence": 0.1}
    i = eng.generate_insight("walk_forward robust", "wf validation is reliable", m, [], T0,
                             commit=True)
    assert i.meta_confidence == HIGH_CONFIDENCE and i.status == GENERATED


def test_insight_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    i = eng.generate_insight("t", "s", {}, [], T0, commit=True)
    eng.transition_insight(i.insight_id, REVIEWED, T1, commit=True)
    eng.transition_insight(i.insight_id, ARCHIVED, T2, commit=True)
    assert eng.insight_state(i.insight_id) == ARCHIVED


def test_insight_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    i = eng.generate_insight("t", "s", {}, [], T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_insight(i.insight_id, ARCHIVED, T1, commit=True)


def test_insight_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownInsight):
        _eng().transition_insight("GHOST", REVIEWED, T1, commit=True)


def test_insight_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_insight("t", "s", {}, [], T0, commit=True)
    eng.generate_insight("t", "s", {}, [], T0, commit=True)
    assert len(ledger.distinct_insights()) == 1


def test_insight_transition_table():
    assert M.can_transition_insight("", GENERATED)
    assert M.can_transition_insight(GENERATED, REVIEWED)
    assert M.can_transition_insight(REVIEWED, ARCHIVED)
    assert not M.can_transition_insight(GENERATED, ARCHIVED)


# ── Meta evaluation framework ──
def test_meta_insight_high():
    m = {"research_reliability": 0.9, "validation_consistency": 0.9, "method_effectiveness": 0.9,
         "evidence_completeness": 0.9, "failure_recurrence": 0.0}
    assert M.meta_insight(m) == HIGH_CONFIDENCE


def test_meta_insight_low():
    m = {"research_reliability": 0.2, "validation_consistency": 0.1, "method_effectiveness": 0.1,
         "evidence_completeness": 0.1, "failure_recurrence": 0.5}
    assert M.meta_insight(m) == LOW_CONFIDENCE


def test_meta_insight_medium():
    m = {"research_reliability": 0.6, "validation_consistency": 0.5, "method_effectiveness": 0.5,
         "evidence_completeness": 0.5, "failure_recurrence": 0.1}
    assert M.meta_insight(m) == MEDIUM_CONFIDENCE


def test_meta_score_failure_penalty():
    base = {"research_reliability": 0.8, "validation_consistency": 0.8,
            "method_effectiveness": 0.8, "evidence_completeness": 0.8}
    hi = M.meta_score({**base, "failure_recurrence": 0.0})
    lo = M.meta_score({**base, "failure_recurrence": 1.0})
    assert hi > lo


def test_meta_positive_weights_sum_one():
    assert abs(sum(M.META_POSITIVE_WEIGHTS.values()) - 1.0) < 1e-9


def test_analyze_research_history(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_outcome("rg", "A", SUCCESS, {"x": 1}, "rv:1", "", T0, commit=True)
    eng.record_outcome("rg", "B", FAILED, {"x": 1}, "", "", T0, commit=True)
    m = eng.analyze_research_history()
    assert m["research_reliability"] == 0.5 and m["failure_recurrence"] == 0.5


def test_analyze_returns_label(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_outcome("rg", "A", SUCCESS, {"x": 1}, "rv:1", "", T0, commit=True)
    res = eng.analyze()
    assert res["meta_insight"] in (HIGH_CONFIDENCE, MEDIUM_CONFIDENCE, LOW_CONFIDENCE)


# ── Evolution graph ──
def test_record_evolution_edge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = eng.record_evolution_edge("M1", M.NODE_METHOD, "E1", M.NODE_EXPERIMENT, M.USED_BY, T0,
                                  commit=True)
    assert e["edge_type"] == M.USED_BY and e["from_ref"] == "M1"


@pytest.mark.parametrize("edge", list(M.EDGE_TYPES))
def test_evolution_edge_types(tmp_path, monkeypatch, edge):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = eng.record_evolution_edge("A", M.NODE_METHOD, "B", M.NODE_EXPERIMENT, edge, T0,
                                  commit=True)
    assert e["edge_type"] == edge


def test_evolution_invalid_node(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(InvalidEvolutionLink):
        eng.record_evolution_edge("A", "NONSENSE", "B", M.NODE_EXPERIMENT, M.USED_BY, T0,
                                  commit=True)


def test_evolution_invalid_edge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(InvalidEvolutionLink):
        eng.record_evolution_edge("A", M.NODE_METHOD, "B", M.NODE_EXPERIMENT, "NONSENSE", T0,
                                  commit=True)


def test_evolution_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_evolution_edge("A", M.NODE_METHOD, "B", M.NODE_EXPERIMENT, M.LED_TO, T0,
                              commit=True)
    eng.record_evolution_edge("B", M.NODE_EXPERIMENT, "C", M.NODE_STRATEGY, M.LED_TO, T0,
                              commit=True)
    with pytest.raises(InvalidEvolutionLink):
        eng.record_evolution_edge("C", M.NODE_STRATEGY, "A", M.NODE_METHOD, M.LED_TO, T0,
                                  commit=True)


def test_evolution_cycle_free(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_evolution_edge("A", M.NODE_METHOD, "B", M.NODE_EXPERIMENT, M.LED_TO, T0,
                              commit=True)
    assert eng.evolution_cycle() == []


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b")]) == []


# ── Report / summary ──
def _full(eng):
    m = eng.register_method(M.WALK_FORWARD_VALIDATION, "1", "validation", 0, 0.0, {}, T0,
                            commit=True)
    eng.register_pattern(M.OVERFITTING, "repeat overfit", 3, [], 0.7, T0, commit=True)
    eng.record_outcome("rg", "ST1", SUCCESS, {"sharpe": 1.2}, "rv:V1", m.method_id, T0,
                       commit=True)
    o2 = eng.record_outcome("rg", "ST2", FAILED, {"sharpe": 0.1}, "", m.method_id, T0,
                            commit=True)
    eng.classify_outcome(o2.outcome_id, T1, commit=True)
    eng.record_failure(M.OVERFITTING, 2, ["ST2"], 0.8, T0, commit=True)
    eng.calculate_quality("ST1", _QUAL, T0, commit=True)
    metrics = eng.analyze_research_history()
    eng.generate_insight("wf method", "wf reliable", metrics, ["rv:V1"], T0, commit=True)
    return m


def test_generate_meta_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_meta_report("GLOBAL", T2, commit=True)
    assert rep.outcome_count == 2 and rep.pattern_count == 1
    assert rep.failure_count == 1 and rep.method_count == 1 and rep.insight_count == 1
    assert "TRADING SCORE" in rep.disclaimer


def test_report_result_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_meta_report("GLOBAL", T2, commit=True)
    assert rep.result_distribution.get(SUCCESS) == 1 and rep.result_distribution.get(FAILED) == 1


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_meta_report("GLOBAL", T2, commit=True)
    d = rep.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d).upper()
    for verb in ("BUY", "SELL", "DEPLOY", "ALLOCATE"):
        assert verb not in blob


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    eng.generate_meta_report("GLOBAL", T2, commit=True)
    eng.generate_meta_report("GLOBAL", T2, commit=True)
    assert len(ledger.read_reports()) == 1


def test_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.summary(T2)
    assert rep.pattern_count == 1 and rep.method_count == 1 and rep.outcome_count == 2
    assert rep.failure_count == 1 and rep.quality_score_count == 1 and rep.insight_count == 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T2).to_dict() == eng.summary(T2).to_dict()


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().summary(T0)
    assert rep.pattern_count == 0 and rep.report_count == 0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.verify import verify_chain
    eng = _eng()
    _full(eng)
    res = verify_chain()
    assert res["ok"] is True and res["lineage"]["ok"] and res["evolution"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.verify import verify_chain
    eng = _eng()
    eng.register_method("m", "1", "", 0, 0.0, {}, T0, commit=True)
    recs = ledger.read_methods()
    recs[0]["name"] = "TAMPERED"
    with open(sp("mi_methods.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.verify import verify_ledger
    eng = _eng()
    eng.register_method("a", "1", "", 0, 0.0, {}, T0, commit=True)
    eng.register_method("b", "1", "", 0, 0.0, {}, T0, commit=True)
    recs = ledger.read_methods()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("mi_methods.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.METHODS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.verify import verify_ledger
    eng = _eng()
    eng.register_method("m", "1", "", 0, 0.0, {}, T0, commit=True)
    recs = ledger.read_methods()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("mi_methods.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.METHODS)["ok"] is False


def test_verify_lineage_broken_parent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.verify import lineage_validation
    rec = {"artifact_id": "A1", "artifact_type": "OUTCOME", "ref_id": "r",
           "parent_artifact": "GHOST", "from_ref": "", "to_ref": "", "edge_type": "",
           "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("mi_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = lineage_validation()
    assert any("broken_lineage" in i for i in res["issues"])


def test_verify_evolution_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.verify import evolution_graph_validation
    a1 = {"artifact_id": "E1", "artifact_type": M.ART_EDGE, "ref_id": "e1", "parent_artifact": "",
          "from_ref": "A", "to_ref": "B", "edge_type": "LED_TO", "created_at": T0,
          "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "E2", "artifact_type": M.ART_EDGE, "ref_id": "e2", "parent_artifact": "",
          "from_ref": "B", "to_ref": "A", "edge_type": "LED_TO", "created_at": T0,
          "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("mi_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    assert evolution_graph_validation()["ok"] is False


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.verify import replay
    eng = _eng()
    _full(eng)
    assert replay(eng, T2)["deterministic"] is True


def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


# ── CLI ──
def test_cli_outcome_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.__main__ import main
    rc = main(["outcome", "--source-layer", "rg", "--research-object", "ST1", "--result-type",
               "SUCCESS", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["outcome"]["result_type"] == "SUCCESS"
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["outcome_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.__main__ import main
    main(["method", "--name", "walk_forward_validation", "--version", "1", "--commit"])
    capsys.readouterr()
    main(["outcome", "--source-layer", "rg", "--research-object", "ST1", "--result-type",
          "SUCCESS", "--commit"])
    capsys.readouterr()
    main(["failure", "--category", "overfitting", "--occurrences", "2", "--commit"])
    capsys.readouterr()
    main(["quality", "--research-object", "ST1", "--components-json", json.dumps(_QUAL),
          "--commit"])
    q = json.loads(capsys.readouterr().out)["quality"]
    assert q["grade"] in ("A", "B", "C", "D")
    main(["insight", "--topic", "t", "--statement", "s", "--metrics-json",
          json.dumps({"research_reliability": 0.9, "validation_consistency": 0.9,
                      "method_effectiveness": 0.9, "evidence_completeness": 0.9,
                      "failure_recurrence": 0.0}), "--commit"])
    ins = json.loads(capsys.readouterr().out)["insight"]
    assert ins["meta_confidence"] == HIGH_CONFIDENCE
    main(["report", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_pattern(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.__main__ import main
    rc = main(["pattern", "--category", "overfitting", "--description", "repeat", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["pattern"]["category"] == "overfitting"


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_intelligence.__main__ import main
    main(["method", "--name", "m", "--version", "1", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.meta_intelligence.engine as eng_mod
    import jarvis.meta_intelligence.models as mdl_mod
    import jarvis.meta_intelligence.ledger as led_mod
    import jarvis.meta_intelligence.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio.", _j + "risk_governor", _j + "permission",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "promote_model(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.meta_intelligence.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def trade", "def allocate", "def deploy", "def promote",
               "def select_strategy", "def activate_live"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchMetaEngine))
    for banned in ("execute", "trade", "allocate", "deploy", "promote", "select_strategy",
                   "activate_live", "approve_for_trading", "place_order"):
        assert banned not in api


def test_meta_score_not_trading_score(tmp_path, monkeypatch):
    """리포트에 trading/permission/allocation 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_meta_report("GLOBAL", T2, commit=True)
    d = rep.to_dict()
    for banned in ("trading_score", "permission", "allocation", "deploy"):
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
        m = importlib.import_module(f"jarvis.meta_intelligence.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_mi_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("mi_")


def test_no_collision_with_existing_prefixes():
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"mg_models.jsonl", "rg_strategies.jsonl", "ai_signals.jsonl", "pr_portfolios.jsonl",
             "kg_entities.jsonl", "di_candidates.jsonl", "sim_scenarios.jsonl",
             "ci_variables.jsonl", "rv_validations.jsonl", "ob_snapshots.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("mi_") and not fn.startswith("mg_") for fn in ours)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, spec in ledger.SOURCE_LEDGERS.items():
        assert spec[0] not in owned


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 P10.2~P10.11 원장을 시드한 뒤 전체 워크플로를 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"rg_experiments.jsonl": [{"experiment_id": "EX1"}],
             "ai_signals.jsonl": [{"signal_id": "SG1"}],
             "ci_evidences.jsonl": [{"evidence_id": "CIE:1"}],
             "sim_results.jsonl": [{"result_id": "SRS:1"}]}
    hashes = {}
    for fn, rows in seeds.items():
        with open(sp(fn), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    refs = eng.list_source_objects("research_governance")
    assert refs == ["research_governance:EX1"]
    _full(eng)
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_engine_only_appends_mi_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("mi_") for f in created)


def test_node_and_edge_types_defined():
    assert "METHOD" in M.NODE_TYPES and "INSIGHT" in M.NODE_TYPES
    assert set(M.EDGE_TYPES) == {"USED_BY", "LED_TO", "FAILED_BECAUSE", "SUPPORTED_BY",
                                 "IMPROVED_BY"}


def test_list_source_objects_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("NOPE") == []
