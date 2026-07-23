"""P10.11 Research Causal Intelligence 테스트. **연구 인과 분석·증거 전용.**

변수(불변)·가설 생명주기(DRAFT→TESTING→EVIDENCED→REVIEWED→ARCHIVED, 차단전이)·관계연구(노드 검증·
순환 차단)·실험 생명주기(CREATED→RUNNING→COMPLETED→ANALYZED)·증거·인과 그래프(REGISTERED→CONNECTED→
SNAPSHOTTED)·인과 분석(STRONG/MODERATE/WEAK/INCONCLUSIVE)·리포트·verify(체인/변조/중복/그래프/계보/
순환/고아)·replay·상위 READ ONLY 보호·CLI·보안(금지import·실행/거래/배포/자본배분/승인 없음·상위 원장
무변경·삭제 API 없음·불변·CAUSAL SCORE≠TRADING PERMISSION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.causal_intelligence import ledger
from jarvis.causal_intelligence import models as M
from jarvis.causal_intelligence.engine import ResearchCausalEngine
from jarvis.causal_intelligence.models import (
    ANALYZED,
    ARCHIVED,
    COMPLETED,
    CONNECTED,
    CREATED,
    DRAFT,
    EVIDENCED,
    INCONCLUSIVE,
    MODERATE,
    REGISTERED,
    REVIEWED,
    RUNNING,
    SNAPSHOTTED,
    STRONG,
    TESTING,
    WEAK,
    CausalCycleError,
    IllegalTransition,
    ImmutableHypothesisError,
    ImmutableVariableError,
    UnknownExperiment,
    UnknownHypothesis,
    UnknownVariable,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_STRONG = {"relationship_strength": 0.9, "temporal_consistency": 0.85, "regime_stability": 0.8,
           "robustness": 0.85, "alternative_explanation_warning": False}
_WEAK = {"relationship_strength": 0.3, "temporal_consistency": 0.2, "regime_stability": 0.2,
         "robustness": 0.3, "alternative_explanation_warning": False}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.causal_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchCausalEngine()


def _var(eng, name="liquidity", vtype=M.VAR_LIQUIDITY, node=M.NODE_VARIABLE, commit=True):
    return eng.register_variable(name, vtype, f"src:{name}", node, {"k": name}, T0, commit=commit)


def _two_vars(eng):
    a = _var(eng, "liquidity", M.VAR_LIQUIDITY)
    b = _var(eng, "drawdown", M.VAR_VOLATILITY)
    return a, b


def _hyp(eng, a, b, stmt="Liquidity reduction increases drawdown", commit=True):
    return eng.create_hypothesis(a.variable_id, b.variable_id, stmt, "mechanism", 0.6, T0,
                                 commit=commit)


# ── Variable ──
def test_register_variable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _var(eng)
    assert v.var_type == M.VAR_LIQUIDITY and v.node_type == M.NODE_VARIABLE


def test_variable_id_deterministic():
    a = M.variable_id("n", "t", "s")
    assert a == M.variable_id("n", "t", "s") and a.startswith("CIV:")


def test_variable_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _var(_eng(), commit=True)
    assert len(ledger.read_variables()) == 1


def test_variable_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _var(_eng(), commit=False)
    assert ledger.read_variables() == []


def test_variable_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_variable("v", "t", "s", "VARIABLE", {"a": 1}, T0, commit=True)
    with pytest.raises(ImmutableVariableError):
        eng.register_variable("v", "t", "s", "VARIABLE", {"a": 2}, T0, commit=True)


def test_variable_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _var(eng)
    _var(eng)
    assert len(ledger.read_variables()) == 1


@pytest.mark.parametrize("vtype", list(M.VARIABLE_TYPES))
def test_variable_types(tmp_path, monkeypatch, vtype):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = eng.register_variable(f"v_{vtype}", vtype, "", "VARIABLE", {}, T0, commit=True)
    assert v.var_type == vtype


def test_variable_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    v = _var(eng)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    va = arts[M.artifact_id(M.ART_VARIABLE, v.variable_id)]
    assert va["parent_artifact"] in arts  # SOURCE 부모 존재


# ── Hypothesis lifecycle ──
def test_create_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    assert h.status == DRAFT and h.cause_variable == a.variable_id
    assert eng.hypothesis_state(h.hypothesis_id) == DRAFT


def test_hypothesis_unknown_cause(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    with pytest.raises(UnknownVariable):
        eng.create_hypothesis("CIV:ghost", b.variable_id, "stmt", "", 0.5, T0, commit=True)


def test_hypothesis_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    eng.create_hypothesis(a.variable_id, b.variable_id, "s", "mech1", 0.5, T0, commit=True)
    with pytest.raises(ImmutableHypothesisError):
        eng.create_hypothesis(a.variable_id, b.variable_id, "s", "mech2", 0.5, T0, commit=True)


def test_hypothesis_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    _hyp(eng, a, b)
    _hyp(eng, a, b)
    assert len(ledger.distinct_hypotheses()) == 1


def test_hypothesis_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    hid = h.hypothesis_id
    eng.transition_hypothesis(hid, TESTING, T1, commit=True)
    eng.transition_hypothesis(hid, EVIDENCED, T1, commit=True)
    eng.transition_hypothesis(hid, REVIEWED, T2, commit=True)
    eng.transition_hypothesis(hid, ARCHIVED, T2, commit=True)
    assert eng.hypothesis_state(hid) == ARCHIVED


def test_hypothesis_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    with pytest.raises(IllegalTransition):
        eng.transition_hypothesis(h.hypothesis_id, EVIDENCED, T1, commit=True)


def test_hypothesis_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    for to in (TESTING, EVIDENCED, REVIEWED, ARCHIVED):
        eng.transition_hypothesis(h.hypothesis_id, to, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_hypothesis(h.hypothesis_id, DRAFT, T2, commit=True)


def test_hypothesis_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownHypothesis):
        _eng().transition_hypothesis("GHOST", TESTING, T1, commit=True)


def test_hypothesis_transition_table():
    assert M.can_transition_hypothesis("", DRAFT)
    assert M.can_transition_hypothesis(DRAFT, TESTING)
    assert M.can_transition_hypothesis(TESTING, EVIDENCED)
    assert not M.can_transition_hypothesis(DRAFT, EVIDENCED)
    assert not M.can_transition_hypothesis(ARCHIVED, DRAFT)


# ── Relationship / graph edges ──
@pytest.mark.parametrize("edge", list(M.EDGE_TYPES))
def test_relationship_edge_types(tmp_path, monkeypatch, edge):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    r = eng.record_relationship(a.variable_id, edge, b.variable_id, "corr", "", "", None, "",
                                T0, commit=True)
    assert r.edge_type == edge


def test_relationship_unknown_node(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    with pytest.raises(UnknownVariable):
        eng.record_relationship(a.variable_id, M.CAUSES, "CIV:ghost", "", "", "", None, "", T0,
                                commit=True)


def test_relationship_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _var(eng, "A", M.VAR_LIQUIDITY)
    b = _var(eng, "B", M.VAR_VOLATILITY)
    c = _var(eng, "C", M.VAR_REGIME)
    eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "", "", "", None, "", T0,
                            commit=True)
    eng.record_relationship(b.variable_id, M.CAUSES, c.variable_id, "", "", "", None, "", T0,
                            commit=True)
    with pytest.raises(CausalCycleError):
        eng.record_relationship(c.variable_id, M.CAUSES, a.variable_id, "", "", "", None, "", T0,
                                commit=True)


def test_relationship_correlated_symmetric_no_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    eng.record_relationship(a.variable_id, M.CORRELATED_WITH, b.variable_id, "", "", "", None,
                            "", T0, commit=True)
    # 대칭 관계는 순환 검사 제외 → 반대 방향도 허용
    r = eng.record_relationship(b.variable_id, M.CORRELATED_WITH, a.variable_id, "", "", "",
                                None, "", T0, commit=True)
    assert r.edge_type == M.CORRELATED_WITH


def test_relationship_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "", "", "", None, "", T0,
                            commit=True)
    eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "", "", "", None, "", T0,
                            commit=True)
    assert len(ledger.read_relationships()) == 1


def test_relationship_invalid_edge_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    with pytest.raises(ValueError):
        eng.record_relationship(a.variable_id, "NONSENSE", b.variable_id, "", "", "", None, "",
                                T0, commit=True)


def test_no_automatic_conclusion_field(tmp_path, monkeypatch):
    """관계연구에 자동 결론/추천 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    r = eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "", "", "", None,
                                "descriptive", T0, commit=True)
    d = r.to_dict()
    for banned in ("recommendation", "action", "conclusion", "decision"):
        assert banned not in d


# ── Experiment lifecycle ──
def test_create_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, M.CORRELATION_ANALYSIS, {"window": 60}, None, T1,
                              commit=True)
    assert x.status == CREATED and x.method == M.CORRELATION_ANALYSIS


def test_create_experiment_advances_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    eng.create_experiment(h.hypothesis_id, M.LAG_ANALYSIS, {}, None, T1, commit=True)
    assert eng.hypothesis_state(h.hypothesis_id) == TESTING


def test_experiment_unknown_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownHypothesis):
        _eng().create_experiment("GHOST", M.CORRELATION_ANALYSIS, {}, None, T1, commit=True)


def test_run_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, M.CORRELATION_ANALYSIS, {}, None, T1, commit=True)
    eng.run_experiment(x.experiment_id, T1, commit=True)
    assert eng.experiment_state(x.experiment_id) == COMPLETED


def test_run_experiment_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownExperiment):
        _eng().run_experiment("GHOST", T1, commit=True)


def test_experiment_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, M.CORRELATION_ANALYSIS, {}, None, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_experiment(x.experiment_id, ANALYZED, T1, commit=True)  # CREATED→ANALYZED


def test_experiment_transition_table():
    assert M.can_transition_experiment("", CREATED)
    assert M.can_transition_experiment(CREATED, RUNNING)
    assert M.can_transition_experiment(RUNNING, COMPLETED)
    assert M.can_transition_experiment(COMPLETED, ANALYZED)
    assert not M.can_transition_experiment(CREATED, COMPLETED)


@pytest.mark.parametrize("method", list(M.EXPERIMENT_METHODS))
def test_experiment_methods(tmp_path, monkeypatch, method):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, method, {"m": method}, None, T1, commit=True)
    assert x.method == method


def test_intervention_simulation_is_record_only(tmp_path, monkeypatch):
    """intervention_simulation 은 기록만 — 실제 개입 메서드가 없다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, M.INTERVENTION_SIMULATION, {}, None, T1,
                              commit=True)
    assert x.method == M.INTERVENTION_SIMULATION
    assert not hasattr(eng, "intervene")


# ── Evidence ──
def test_record_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, M.CORRELATION_ANALYSIS, {}, None, T1, commit=True)
    e = eng.record_evidence(x.experiment_id, "correlation", 0.62, "moderate", 0.7, T1,
                            commit=True)
    assert e.value == 0.62 and e.metric == "correlation"
    assert len(ledger.read_evidences()) == 1


def test_evidence_advances_experiment_and_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, M.CORRELATION_ANALYSIS, {}, None, T1, commit=True)
    eng.record_evidence(x.experiment_id, "corr", 0.5, "", 0.5, T1, commit=True)
    assert eng.experiment_state(x.experiment_id) == ANALYZED
    assert eng.hypothesis_state(h.hypothesis_id) == EVIDENCED


def test_evidence_unknown_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownExperiment):
        _eng().record_evidence("GHOST", "m", 0.1, "", 0.1, T1, commit=True)


def test_evidence_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, M.CORRELATION_ANALYSIS, {}, None, T1, commit=True)
    eng.record_evidence(x.experiment_id, "corr", 0.5, "", 0.5, T1, commit=True)
    eng.record_evidence(x.experiment_id, "corr", 0.5, "", 0.5, T1, commit=True)
    assert len(ledger.read_evidences()) == 1


def test_evidence_descriptive_only(tmp_path, monkeypatch):
    """증거에 action/deploy/allocate 필드가 없어야 한다 — 서술 전용."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, M.CORRELATION_ANALYSIS, {}, None, T1, commit=True)
    e = eng.record_evidence(x.experiment_id, "corr", 0.5, "", 0.5, T1, commit=True)
    for banned in ("action", "deploy", "allocate", "trade"):
        assert banned not in e.to_dict()


# ── Causal graph snapshot ──
def test_snapshot_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "", "", "", None, "", T0,
                            commit=True)
    g = eng.snapshot_graph("causal_v1", T1, commit=True)
    assert g.node_count == 2 and g.edge_count == 1
    assert eng.graph_state(g.graph_id) == SNAPSHOTTED


def test_graph_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "", "", "", None, "", T0,
                            commit=True)
    g = eng.snapshot_graph("g", T1, commit=True)
    assert g.node_distribution.get("VARIABLE") == 2
    assert g.edge_distribution.get(M.CAUSES) == 1


def test_graph_deterministic_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "", "", "", None, "", T0,
                            commit=True)
    g1 = eng.snapshot_graph("g", T1, commit=True)
    g2 = eng.snapshot_graph("g", T1, commit=True)
    assert g1.graph_hash == g2.graph_hash


def test_graph_lifecycle_states(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_vars(eng)
    g = eng.snapshot_graph("g", T1, commit=True)
    evs = ledger.graph_events_for(g.graph_id)
    states = [e["to_state"] for e in evs]
    assert states == [REGISTERED, CONNECTED, SNAPSHOTTED]


def test_graph_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "", "", "", None, "", T0,
                            commit=True)
    assert eng.graph_cycle() == []  # DAG


def test_orphan_variables(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    c = _var(eng, "orphan", M.VAR_REGIME)
    eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "", "", "", None, "", T0,
                            commit=True)
    assert eng.orphan_variables() == [c.variable_id]


def test_graph_hash_helper():
    assert M.graph_hash(["a", "b"], [("a", "b")]) == M.graph_hash(["b", "a"], [("a", "b")])


# ── Causal analysis framework ──
def test_causal_support_strong():
    assert M.causal_support(_STRONG) == STRONG


def test_causal_support_weak():
    assert M.causal_support(_WEAK) == WEAK


def test_causal_support_inconclusive():
    m = {"relationship_strength": 0.1, "temporal_consistency": 0.1, "regime_stability": 0.1,
         "robustness": 0.1}
    assert M.causal_support(m) == INCONCLUSIVE


def test_causal_support_alt_warning_caps():
    m = dict(_STRONG)
    m["alternative_explanation_warning"] = True
    assert M.causal_support(m) == MODERATE  # 강해도 경고 시 MODERATE 상한


def test_causal_score_weighted():
    m = {"relationship_strength": 1.0, "temporal_consistency": 0.0, "regime_stability": 0.0,
         "robustness": 0.0}
    assert abs(M.causal_score(m) - 0.35) < 1e-9


def test_causal_weights_sum_one():
    assert abs(sum(M.CAUSAL_WEIGHTS.values()) - 1.0) < 1e-9


def test_analyze_causality(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze_causality(_STRONG)
    assert res["causal_support"] == STRONG and 0.0 <= res["causal_score"] <= 1.0


def test_causal_support_never_trading_keyword():
    for m in (_STRONG, _WEAK):
        assert M.causal_support(m) in (STRONG, M.MODERATE, WEAK, INCONCLUSIVE)


# ── Report ──
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    x = eng.create_experiment(h.hypothesis_id, M.CORRELATION_ANALYSIS, {}, None, T1, commit=True)
    eng.record_evidence(x.experiment_id, "corr", 0.7, "", 0.7, T1, commit=True)
    rep = eng.generate_report(h.hypothesis_id, _STRONG, T2, commit=True)
    assert rep.causal_support == STRONG and rep.evidence_count == 1
    assert "TRADING PERMISSION" in rep.disclaimer


def test_report_unknown_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownHypothesis):
        _eng().generate_report("GHOST", {}, T2, commit=True)


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    """리포트 어디에도 BUY/SELL/DEPLOY/ENABLE/ALLOCATE 가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    rep = eng.generate_report(h.hypothesis_id, _STRONG, T2, commit=True)
    d = rep.to_dict()
    d.pop("disclaimer")  # disclaimer 는 "BUY/SELL 아님" 부인 문구 — 지시가 아님
    blob = json.dumps(d).upper()
    for verb in ("BUY", "SELL", "DEPLOY", "ENABLE", "ALLOCATE"):
        assert verb not in blob
    # 출력 라벨은 오직 STRONG/MODERATE/WEAK/INCONCLUSIVE 만.
    assert rep.causal_support in (STRONG, MODERATE, WEAK, INCONCLUSIVE)


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    eng.generate_report(h.hypothesis_id, _STRONG, T2, commit=True)
    eng.generate_report(h.hypothesis_id, _STRONG, T2, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_alt_warning_flag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    m = dict(_STRONG)
    m["alternative_explanation_warning"] = True
    rep = eng.generate_report(h.hypothesis_id, m, T2, commit=True)
    assert rep.alternative_explanation_warning is True and rep.causal_support == MODERATE


# ── Summary ──
def _full(eng):
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    eng.record_relationship(a.variable_id, M.CAUSES, b.variable_id, "corr", "", "", None, "", T0,
                            commit=True)
    x = eng.create_experiment(h.hypothesis_id, M.CORRELATION_ANALYSIS, {"w": 60}, None, T1,
                              commit=True)
    eng.record_evidence(x.experiment_id, "corr", 0.7, "moderate", 0.7, T1, commit=True)
    eng.snapshot_graph("g", T1, commit=True)
    eng.generate_report(h.hypothesis_id, _STRONG, T2, commit=True)
    return a, b, h, x


def test_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.summary(T2)
    assert rep.variable_count == 2 and rep.hypothesis_count == 1
    assert rep.relationship_count == 1 and rep.experiment_count == 1
    assert rep.evidence_count == 1 and rep.graph_count == 1 and rep.report_count == 1


def test_summary_support_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.summary(T2)
    assert rep.support_distribution.get(STRONG) == 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T2).to_dict() == eng.summary(T2).to_dict()


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().summary(T0)
    assert rep.variable_count == 0 and rep.report_count == 0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.verify import verify_chain
    eng = _eng()
    _full(eng)
    res = verify_chain()
    assert res["ok"] is True
    assert res["graph"]["ok"] and res["lineage"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.verify import verify_chain
    eng = _eng()
    _var(eng)
    recs = ledger.read_variables()
    recs[0]["name"] = "TAMPERED"
    with open(sp("ci_variables.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.verify import verify_ledger
    eng = _eng()
    _var(eng, "a")
    _var(eng, "b")
    recs = ledger.read_variables()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("ci_variables.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.VARIABLES)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.verify import verify_ledger
    eng = _eng()
    _var(eng)
    recs = ledger.read_variables()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("ci_variables.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.VARIABLES)["ok"] is False


def test_verify_graph_unknown_node(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.verify import graph_validation
    _seed = {"study_id": "CIR:x", "cause": "CIV:ghost", "effect": "CIV:ghost2",
             "edge_type": M.CAUSES, "methodology": "", "dataset_reference": "", "period": "",
             "controls": [], "result": "", "created_at": T0, "previous_hash": "GENESIS"}
    _seed["record_hash"] = M.content_hash(_seed)
    # 변수 하나 등록해 variable_ids 비어있지 않게
    ResearchCausalEngine().register_variable("v", "t", "s", "VARIABLE", {}, T0, commit=True)
    with open(sp("ci_relationships.jsonl"), "w") as f:
        f.write(json.dumps(_seed) + "\n")
    res = graph_validation()
    assert res["ok"] is False
    assert any("unknown_node" in i for i in res["issues"])


def test_verify_lineage_dangling_experiment(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.verify import lineage_validation
    rec = {"event_id": "CXE:x", "experiment_id": "CIX:x", "hypothesis_id": "CIH:ghost",
           "method": "correlation_analysis", "inputs": {}, "controls": [], "results": {},
           "from_state": "", "to_state": "CREATED", "status": "CREATED", "created_at": T0,
           "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("ci_experiments.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = lineage_validation()
    assert any("dangling_experiment" in i for i in res["issues"])


def test_verify_artifact_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.verify import lineage_validation
    a1 = {"artifact_id": "A1", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A2",
          "created_at": T0, "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "A2", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A1",
          "created_at": T0, "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("ci_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    assert any("artifact_cycle" in i for i in lineage_validation()["issues"])


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b")]) == []


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.verify import replay
    eng = _eng()
    _full(eng)
    assert replay(eng, T2)["deterministic"] is True


def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


# ── CLI ──
def test_cli_variable_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.__main__ import main
    rc = main(["variable", "--name", "liquidity", "--type", "liquidity", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["variable"]["name"] == "liquidity"
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["variable_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.__main__ import main
    main(["variable", "--name", "liq", "--type", "liquidity", "--source-ref", "s1", "--commit"])
    ca = json.loads(capsys.readouterr().out)["variable"]["variable_id"]
    main(["variable", "--name", "dd", "--type", "volatility", "--source-ref", "s2", "--commit"])
    cb = json.loads(capsys.readouterr().out)["variable"]["variable_id"]
    main(["hypothesis", "--cause", ca, "--effect", cb, "--statement", "liq->dd", "--commit"])
    hid = json.loads(capsys.readouterr().out)["hypothesis"]["hypothesis_id"]
    main(["relationship", "--cause", ca, "--edge-type", "CAUSES", "--effect", cb, "--commit"])
    capsys.readouterr()
    main(["experiment", "--hypothesis-id", hid, "--method", "correlation_analysis", "--run",
          "--commit"])
    xid = json.loads(capsys.readouterr().out)["experiment"]["experiment_id"]
    main(["evidence", "--experiment-id", xid, "--metric", "corr", "--value", "0.7", "--commit"])
    capsys.readouterr()
    main(["graph", "--name", "g1", "--commit"])
    g = json.loads(capsys.readouterr().out)
    assert g["cycle"] == []
    main(["report", "--hypothesis-id", hid, "--metrics-json",
          json.dumps({"relationship_strength": 0.9, "temporal_consistency": 0.9,
                      "regime_stability": 0.9, "robustness": 0.9}), "--commit"])
    rep = json.loads(capsys.readouterr().out)["report"]
    assert rep["causal_support"] == STRONG
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_lineage(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.__main__ import main
    _full(_eng())
    rc = main(["lineage"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["graph"]["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.causal_intelligence.__main__ import main
    main(["variable", "--name", "v", "--type", "liquidity", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.causal_intelligence.engine as eng_mod
    import jarvis.causal_intelligence.models as mdl_mod
    import jarvis.causal_intelligence.ledger as led_mod
    import jarvis.causal_intelligence.verify as ver_mod
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


def test_no_execution_keywords_in_source():
    """엔진/모델 소스에 실행/거래 동사가 메서드로 존재하지 않아야 한다."""
    import jarvis.causal_intelligence.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def trade", "def allocate", "def deploy", "def promote",
               "def activate_live", "def approve_for_trading"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchCausalEngine))
    for banned in ("execute", "trade", "allocate", "deploy", "promote", "activate_live",
                   "approve_for_trading", "select_strategy", "place_order", "intervene"):
        assert banned not in api


def test_causal_score_not_trading_permission(tmp_path, monkeypatch):
    """리포트에 permission/trading/approval 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_vars(eng)
    h = _hyp(eng, a, b)
    rep = eng.generate_report(h.hypothesis_id, _STRONG, T2, commit=True)
    d = rep.to_dict()
    for banned in ("trading_permission", "approved", "deployable", "permission"):
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
        m = importlib.import_module(f"jarvis.causal_intelligence.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_ci_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("ci_")


def test_no_collision_with_existing_prefixes():
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"rg_strategies.jsonl", "ai_signals.jsonl", "pr_portfolios.jsonl",
             "kg_entities.jsonl", "di_candidates.jsonl", "sim_scenarios.jsonl",
             "rv_validations.jsonl", "ob_snapshots.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("ci_") for fn in ours)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, spec in ledger.SOURCE_LEDGERS.items():
        assert spec[0] not in owned


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 P10.2~P10.8 원장을 시드한 뒤 전체 워크플로를 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"rg_strategies.jsonl": [{"strategy_id": "ST1"}],
             "ai_signals.jsonl": [{"signal_id": "SG1"}],
             "kg_entities.jsonl": [{"entity_id": "KGE:1"}],
             "sim_scenarios.jsonl": [{"event_id": "E1", "scenario_id": "SSC:1"}]}
    hashes = {}
    for fn, rows in seeds.items():
        with open(sp(fn), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    refs = eng.list_source_references("research_governance")
    assert refs == ["research_governance:ST1"]
    _full(eng)
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_engine_only_appends_ci_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("ci_") for f in created)


def test_node_and_edge_types_defined():
    assert "VARIABLE" in M.NODE_TYPES and "STRATEGY" in M.NODE_TYPES
    assert set(M.DIRECTED_EDGES).issubset(set(M.EDGE_TYPES))
    assert M.CORRELATED_WITH not in M.DIRECTED_EDGES


def test_list_source_references_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_references("NOPE") == []
