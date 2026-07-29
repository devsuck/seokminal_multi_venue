"""P10.13 Research Self-Improvement Intelligence 테스트. **연구 과정 최적화 분석 전용.**

워크플로(불변)·개선 기회 생명주기(IDENTIFIED→ANALYZED→REVIEWED→ARCHIVED, 차단전이)·병목·권고 생명주기
(CREATED→REVIEWED→ACCEPTED→ARCHIVED, ACCEPTED=사람 인지)·템플릿 진화·증거·개선 그래프(노드/엣지 검증·
순환)·리포트·verify(체인/변조/중복/계보/순환)·replay·상위 READ ONLY 보호·CLI·보안(금지import·실행/거래/
배포/수정/선택 없음·상위 원장 무변경·삭제 API 없음·불변·SUGGESTION≠ACTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.self_improvement_intelligence import ledger
from jarvis.self_improvement_intelligence import models as M
from jarvis.self_improvement_intelligence.engine import ResearchSelfImprovementEngine
from jarvis.self_improvement_intelligence.models import (
    ACCEPTED,
    ANALYZED,
    ARCHIVED,
    CREATED,
    HIGH,
    IDENTIFIED,
    LOW,
    MEDIUM,
    REVIEWED,
    IllegalTransition,
    ImmutableBottleneckError,
    ImmutableOpportunityError,
    ImmutableTemplateError,
    ImmutableWorkflowError,
    InvalidImprovementLink,
    UnknownOpportunity,
    UnknownRecommendation,
    UnknownWorkflow,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"workflow_efficiency": 0.9, "validation_completeness": 0.85, "research_reproducibility": 0.9,
       "failure_prevention": 0.8, "evidence_coverage": 0.85}
_LO = {"workflow_efficiency": 0.2, "validation_completeness": 0.2, "research_reproducibility": 0.1,
       "failure_prevention": 0.1, "evidence_coverage": 0.2}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.self_improvement_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchSelfImprovementEngine()


def _wf(eng, name="strategy_research", steps=None, ref="rg:ST1", commit=True):
    return eng.register_workflow(name, steps or ["hypothesis", "backtest", "validate"], ref, [],
                                 {}, T0, commit=commit)


def _opp(eng, cat=None, desc="missing wf validation", sev=MEDIUM, commit=True):
    return eng.record_opportunity(cat or M.MISSING_WALK_FORWARD, desc, sev, [], 0.6, "", T0,
                                  commit=commit)


def _rec(eng, tp="backtest", sug="add walk-forward", commit=True):
    return eng.create_recommendation(tp, sug, "reduce overfit", [], 0.7, "", T0, commit=commit)


# ── Workflow ──
def test_register_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    assert w.name == "strategy_research" and "backtest" in w.steps


def test_workflow_id_deterministic():
    a = M.workflow_id("n", "s")
    assert a == M.workflow_id("n", "s") and a.startswith("SIW:")


def test_workflow_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _wf(_eng())
    assert len(ledger.read_workflows()) == 1


def test_workflow_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _wf(_eng(), commit=False)
    assert ledger.read_workflows() == []


def test_workflow_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_workflow("w", ["a"], "s", [], {}, T0, commit=True)
    with pytest.raises(ImmutableWorkflowError):
        eng.register_workflow("w", ["a", "b"], "s", [], {}, T0, commit=True)


def test_workflow_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _wf(eng)
    _wf(eng)
    assert len(ledger.read_workflows()) == 1


def test_compare_workflows(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.register_workflow("A", ["hypothesis", "backtest"], "s1", [], {}, T0, commit=True)
    b = eng.register_workflow("B", ["hypothesis", "backtest", "walk_forward"], "s2", [], {}, T0,
                              commit=True)
    diff = eng.compare_workflows(a.workflow_id, b.workflow_id)
    assert diff["diff"]["only_b"] == ["walk_forward"]
    assert "shared" in diff["diff"]


def test_compare_workflows_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _wf(eng)
    with pytest.raises(UnknownWorkflow):
        eng.compare_workflows(a.workflow_id, "GHOST")


def test_workflow_diff_helper():
    d = M.workflow_diff(["a", "b"], ["b", "c"])
    assert d["only_a"] == ["a"] and d["only_b"] == ["c"] and d["shared"] == ["b"]


def test_workflow_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    wa = arts[M.artifact_id(M.ART_WORKFLOW, w.workflow_id)]
    assert wa["parent_artifact"] in arts


# ── Opportunity lifecycle ──
def test_record_opportunity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    assert o.status == IDENTIFIED and o.severity == MEDIUM


@pytest.mark.parametrize("cat", list(M.OPPORTUNITY_CATEGORIES))
def test_opportunity_categories(tmp_path, monkeypatch, cat):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = eng.record_opportunity(cat, f"desc {cat}", MEDIUM, [], 0.5, "", T0, commit=True)
    assert o.category == cat


@pytest.mark.parametrize("sev", list(M.SEVERITIES))
def test_opportunity_severities(tmp_path, monkeypatch, sev):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = eng.record_opportunity("c", f"d{sev}", sev, [], 0.5, "", T0, commit=True)
    assert o.severity == sev


def test_opportunity_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_opportunity("c", "d", MEDIUM, [], 0.5, "", T0, commit=True)
    with pytest.raises(ImmutableOpportunityError):
        eng.record_opportunity("c", "d", HIGH, [], 0.5, "", T0, commit=True)


def test_opportunity_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _opp(eng)
    _opp(eng)
    assert len(ledger.distinct_opportunities()) == 1


def test_opportunity_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    oid = o.opportunity_id
    eng.transition_opportunity(oid, ANALYZED, T1, commit=True)
    eng.transition_opportunity(oid, REVIEWED, T1, commit=True)
    eng.transition_opportunity(oid, ARCHIVED, T2, commit=True)
    assert eng.opportunity_state(oid) == ARCHIVED


def test_opportunity_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_opportunity(o.opportunity_id, REVIEWED, T1, commit=True)


def test_opportunity_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    for to in (ANALYZED, REVIEWED, ARCHIVED):
        eng.transition_opportunity(o.opportunity_id, to, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_opportunity(o.opportunity_id, IDENTIFIED, T2, commit=True)


def test_opportunity_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownOpportunity):
        _eng().transition_opportunity("GHOST", ANALYZED, T1, commit=True)


def test_opportunity_transition_table():
    assert M.can_transition_opportunity("", IDENTIFIED)
    assert M.can_transition_opportunity(IDENTIFIED, ANALYZED)
    assert M.can_transition_opportunity(ANALYZED, REVIEWED)
    assert not M.can_transition_opportunity(IDENTIFIED, REVIEWED)


# ── Bottleneck ──
def test_analyze_bottleneck(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = eng.analyze_bottleneck(M.REPEATED_FAILED_EXPERIMENTS, 7, "HIGH", ["ST1", "ST2"], T0,
                               commit=True)
    assert b.bottleneck_type == M.REPEATED_FAILED_EXPERIMENTS and b.frequency == 7


@pytest.mark.parametrize("bt", list(M.BOTTLENECK_TYPES))
def test_bottleneck_types(tmp_path, monkeypatch, bt):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = eng.analyze_bottleneck(bt, 1, "LOW", [], T0, commit=True)
    assert b.bottleneck_type == bt


def test_bottleneck_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.analyze_bottleneck("t", 1, "HIGH", ["a"], T0, commit=True)
    with pytest.raises(ImmutableBottleneckError):
        eng.analyze_bottleneck("t", 9, "HIGH", ["a"], T0, commit=True)


def test_bottleneck_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.analyze_bottleneck("t", 1, "HIGH", [], T0, commit=True)
    eng.analyze_bottleneck("t", 1, "HIGH", [], T0, commit=True)
    assert len(ledger.read_bottlenecks()) == 1


def test_opportunity_linked_to_bottleneck(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = eng.analyze_bottleneck("t", 1, "HIGH", [], T0, commit=True)
    o = eng.record_opportunity("c", "d", MEDIUM, [], 0.5, b.bottleneck_id, T0, commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    oa = arts[M.artifact_id(M.ART_OPPORTUNITY, o.opportunity_id)]
    assert oa["parent_artifact"] == M.artifact_id(M.ART_BOTTLENECK, b.bottleneck_id)


# ── Recommendation lifecycle ──
def test_create_recommendation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rec(eng)
    assert r.status == CREATED and r.target_process == "backtest"


def test_recommendation_no_automatic_application(tmp_path, monkeypatch):
    """권고는 자동 적용 없음 — apply/execute 메서드 부재."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _rec(eng)
    assert not hasattr(eng, "apply_recommendation")
    assert not hasattr(eng, "execute_recommendation")


def test_recommendation_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rec(eng)
    rid = r.recommendation_id
    eng.transition_recommendation(rid, REVIEWED, T1, commit=True)
    eng.transition_recommendation(rid, ACCEPTED, T1, commit=True)
    eng.transition_recommendation(rid, ARCHIVED, T2, commit=True)
    assert eng.recommendation_state(rid) == ARCHIVED


def test_accept_recommendation_human_ack(tmp_path, monkeypatch):
    """ACCEPTED 는 사람 인지일 뿐 — 어떤 자동 변경도 없다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rec(eng)
    eng.accept_recommendation(r.recommendation_id, T1, commit=True)
    assert eng.recommendation_state(r.recommendation_id) == ACCEPTED


def test_recommendation_reviewed_to_archived(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rec(eng)
    eng.transition_recommendation(r.recommendation_id, REVIEWED, T1, commit=True)
    eng.transition_recommendation(r.recommendation_id, ARCHIVED, T1, commit=True)
    assert eng.recommendation_state(r.recommendation_id) == ARCHIVED


def test_recommendation_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rec(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_recommendation(r.recommendation_id, ACCEPTED, T1, commit=True)


def test_recommendation_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRecommendation):
        _eng().transition_recommendation("GHOST", REVIEWED, T1, commit=True)


def test_recommendation_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _rec(eng)
    _rec(eng)
    assert len(ledger.distinct_recommendations()) == 1


def test_recommendation_transition_table():
    assert M.can_transition_recommendation("", CREATED)
    assert M.can_transition_recommendation(CREATED, REVIEWED)
    assert M.can_transition_recommendation(REVIEWED, ACCEPTED)
    assert M.can_transition_recommendation(REVIEWED, ARCHIVED)
    assert not M.can_transition_recommendation(CREATED, ACCEPTED)


def test_recommendation_linked_to_opportunity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    r = eng.create_recommendation("backtest", "add wf", "", [], 0.7, o.opportunity_id, T0,
                                  commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    ra = arts[M.artifact_id(M.ART_RECOMMENDATION, r.recommendation_id)]
    assert ra["parent_artifact"] == M.artifact_id(M.ART_OPPORTUNITY, o.opportunity_id)


# ── Template ──
def test_track_template_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    t = eng.track_template_change("experiment_template", "2", ["add wf step"], "reduce overfit",
                                  [], "1", T0, commit=True)
    assert t.version == "2" and t.parent_version == "1"


def test_template_versioning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    t1 = eng.track_template_change("exp", "1", ["a"], "r1", [], "", T0, commit=True)
    t2 = eng.track_template_change("exp", "2", ["a", "b"], "r2", [], "1", T0, commit=True)
    assert t1.template_id != t2.template_id
    assert len(ledger.read_templates()) == 2


def test_template_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.track_template_change("exp", "1", ["a"], "r", [], "", T0, commit=True)
    with pytest.raises(ImmutableTemplateError):
        eng.track_template_change("exp", "1", ["a", "b"], "r", [], "", T0, commit=True)


def test_template_no_auto_migration(tmp_path, monkeypatch):
    """템플릿 변경은 자동 마이그레이션 없음 — migrate 메서드 부재."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    assert not hasattr(eng, "migrate_template")
    assert not hasattr(eng, "apply_template")


# ── Evidence ──
def test_record_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rec(eng)
    e = eng.record_evidence(r.recommendation_id, "backtest_gap", "coverage", 0.4,
                            "low coverage", T1, commit=True)
    assert e.value == 0.4 and e.name == "backtest_gap"
    assert len(ledger.read_evidences()) == 1


def test_evidence_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rec(eng)
    eng.record_evidence(r.recommendation_id, "e", "m", 0.1, "", T1, commit=True)
    eng.record_evidence(r.recommendation_id, "e", "m", 0.1, "", T1, commit=True)
    assert len(ledger.read_evidences()) == 1


def test_evidence_lineage_to_recommendation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rec(eng)
    e = eng.record_evidence(r.recommendation_id, "e", "m", 0.1, "", T1, commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    ea = arts[M.artifact_id(M.ART_EVIDENCE, e.evidence_id)]
    assert ea["parent_artifact"] == M.artifact_id(M.ART_RECOMMENDATION, r.recommendation_id)


# ── Improvement analysis framework ──
def test_improvement_score_full():
    comps = {k: 1.0 for k in M.IMPROVEMENT_WEIGHTS}
    assert abs(M.improvement_score(comps) - 1.0) < 1e-9


def test_improvement_weights_sum_one():
    assert abs(sum(M.IMPROVEMENT_WEIGHTS.values()) - 1.0) < 1e-9


def test_improvement_confidence_high():
    assert M.improvement_confidence(_HI) == HIGH


def test_improvement_confidence_low():
    assert M.improvement_confidence(_LO) == LOW


def test_improvement_confidence_medium():
    m = {k: 0.5 for k in M.IMPROVEMENT_WEIGHTS}
    assert M.improvement_confidence(m) == MEDIUM


def test_analyze_returns_confidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HI)
    assert res["improvement_confidence"] == HIGH


def test_analyze_never_auto_fix():
    for m in (_HI, _LO):
        assert M.improvement_confidence(m) in (HIGH, MEDIUM, LOW)


# ── Improvement graph ──
def test_record_improvement_edge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = eng.record_improvement_edge("F1", M.NODE_FAILURE, "O1", M.NODE_OPPORTUNITY, M.CAUSED_BY,
                                    T0, commit=True)
    assert e["edge_type"] == M.CAUSED_BY


@pytest.mark.parametrize("edge", list(M.EDGE_TYPES))
def test_improvement_edge_types(tmp_path, monkeypatch, edge):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = eng.record_improvement_edge("A", M.NODE_WORKFLOW, "B", M.NODE_OPPORTUNITY, edge, T0,
                                    commit=True)
    assert e["edge_type"] == edge


def test_improvement_invalid_node(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(InvalidImprovementLink):
        eng.record_improvement_edge("A", "NONSENSE", "B", M.NODE_OPPORTUNITY, M.CAUSED_BY, T0,
                                    commit=True)


def test_improvement_invalid_edge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(InvalidImprovementLink):
        eng.record_improvement_edge("A", M.NODE_WORKFLOW, "B", M.NODE_OPPORTUNITY, "NONSENSE",
                                    T0, commit=True)


def test_improvement_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_improvement_edge("A", M.NODE_WORKFLOW, "B", M.NODE_OPPORTUNITY, M.IMPROVES, T0,
                                commit=True)
    eng.record_improvement_edge("B", M.NODE_OPPORTUNITY, "C", M.NODE_RECOMMENDATION, M.IMPROVES,
                                T0, commit=True)
    with pytest.raises(InvalidImprovementLink):
        eng.record_improvement_edge("C", M.NODE_RECOMMENDATION, "A", M.NODE_WORKFLOW, M.IMPROVES,
                                    T0, commit=True)


def test_improvement_cycle_free(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_improvement_edge("A", M.NODE_WORKFLOW, "B", M.NODE_OPPORTUNITY, M.IMPROVES, T0,
                                commit=True)
    assert eng.improvement_cycle() == []


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b")]) == []


# ── Report / summary ──
def _full(eng):
    _wf(eng)
    b = eng.analyze_bottleneck(M.REPEATED_FAILED_EXPERIMENTS, 5, "HIGH", ["ST2"], T0, commit=True)
    o = eng.record_opportunity(M.MISSING_WALK_FORWARD, "no wf validation", "HIGH", ["ST2"], 0.7,
                               b.bottleneck_id, T0, commit=True)
    r = eng.create_recommendation("backtest", "add walk-forward", "reduce overfit", ["ST2"], 0.8,
                                  o.opportunity_id, T0, commit=True)
    eng.accept_recommendation(r.recommendation_id, T1, commit=True)
    eng.record_evidence(r.recommendation_id, "coverage_gap", "coverage", 0.4, "", T1, commit=True)
    eng.track_template_change("experiment_template", "2", ["add wf"], "reduce overfit", [], "1",
                              T0, commit=True)
    return b, o, r


def test_generate_improvement_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_improvement_report("GLOBAL", _HI, T2, commit=True)
    assert rep.workflow_count == 1 and rep.bottleneck_count == 1
    assert rep.opportunity_count == 1 and rep.recommendation_count == 1
    assert rep.template_count == 1 and rep.improvement_confidence == HIGH
    assert "SUGGESTION" in rep.disclaimer


def test_report_severity_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_improvement_report("GLOBAL", _HI, T2, commit=True)
    assert rep.opportunity_severity_distribution.get("HIGH") == 1


def test_report_recommendation_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_improvement_report("GLOBAL", _HI, T2, commit=True)
    assert rep.recommendation_state_distribution.get(ACCEPTED) == 1


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_improvement_report("GLOBAL", _HI, T2, commit=True)
    d = rep.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d).upper()
    for verb in ("AUTO_FIX", "AUTO_APPLY", "DEPLOY", "BUY", "SELL"):
        assert verb not in blob


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    eng.generate_improvement_report("GLOBAL", _HI, T2, commit=True)
    eng.generate_improvement_report("GLOBAL", _HI, T2, commit=True)
    assert len(ledger.read_reports()) == 1


def test_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.summary(T2)
    assert rep.workflow_count == 1 and rep.opportunity_count == 1
    assert rep.recommendation_count == 1 and rep.evidence_count == 1 and rep.template_count == 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T2).to_dict() == eng.summary(T2).to_dict()


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().summary(T0)
    assert rep.workflow_count == 0 and rep.report_count == 0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.verify import verify_chain
    eng = _eng()
    _full(eng)
    res = verify_chain()
    assert res["ok"] is True and res["lineage"]["ok"] and res["improvement"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.verify import verify_chain
    eng = _eng()
    _wf(eng)
    recs = ledger.read_workflows()
    recs[0]["name"] = "TAMPERED"
    with open(sp("si_workflows.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.verify import verify_ledger
    eng = _eng()
    eng.register_workflow("a", ["x"], "s1", [], {}, T0, commit=True)
    eng.register_workflow("b", ["y"], "s2", [], {}, T0, commit=True)
    recs = ledger.read_workflows()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("si_workflows.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.WORKFLOWS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.verify import verify_ledger
    eng = _eng()
    _wf(eng)
    recs = ledger.read_workflows()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("si_workflows.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.WORKFLOWS)["ok"] is False


def test_verify_lineage_broken_parent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.verify import lineage_validation
    rec = {"artifact_id": "A1", "artifact_type": "OPPORTUNITY", "ref_id": "r",
           "parent_artifact": "GHOST", "from_ref": "", "to_ref": "", "edge_type": "",
           "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("si_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = lineage_validation()
    assert any("broken_lineage" in i for i in res["issues"])


def test_verify_improvement_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.verify import improvement_graph_validation
    a1 = {"artifact_id": "E1", "artifact_type": M.ART_EDGE, "ref_id": "e1", "parent_artifact": "",
          "from_ref": "A", "to_ref": "B", "edge_type": "IMPROVES", "created_at": T0,
          "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "E2", "artifact_type": M.ART_EDGE, "ref_id": "e2", "parent_artifact": "",
          "from_ref": "B", "to_ref": "A", "edge_type": "IMPROVES", "created_at": T0,
          "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("si_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    assert improvement_graph_validation()["ok"] is False


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.verify import replay
    eng = _eng()
    _full(eng)
    assert replay(eng, T2)["deterministic"] is True


def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


# ── CLI ──
def test_cli_workflow_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.__main__ import main
    rc = main(["workflow", "--name", "wf1", "--steps", "hypothesis,backtest", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["workflow"]["name"] == "wf1"
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["workflow_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.__main__ import main
    main(["workflow", "--name", "wf1", "--steps", "hypothesis,backtest", "--commit"])
    capsys.readouterr()
    main(["bottleneck", "--type", "repeated_failed_experiments", "--frequency", "5",
          "--impact", "HIGH", "--commit"])
    capsys.readouterr()
    main(["opportunity", "--category", "missing_walk_forward_validation", "--description",
          "no wf", "--severity", "HIGH", "--commit"])
    capsys.readouterr()
    main(["recommendation", "--target-process", "backtest", "--suggestion", "add wf",
          "--accept", "--commit"])
    rec = json.loads(capsys.readouterr().out)["recommendation"]
    assert rec["target_process"] == "backtest"
    main(["report", "--metrics-json", json.dumps({"workflow_efficiency": 0.9,
          "validation_completeness": 0.9, "research_reproducibility": 0.9,
          "failure_prevention": 0.9, "evidence_coverage": 0.9}), "--commit"])
    rep = json.loads(capsys.readouterr().out)["report"]
    assert rep["improvement_confidence"] == HIGH
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_template(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.__main__ import main
    rc = main(["template", "--name", "exp", "--version", "2", "--reason", "improve", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["template"]["version"] == "2"


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_improvement_intelligence.__main__ import main
    main(["workflow", "--name", "w", "--steps", "a", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.self_improvement_intelligence.engine as eng_mod
    import jarvis.self_improvement_intelligence.models as mdl_mod
    import jarvis.self_improvement_intelligence.ledger as led_mod
    import jarvis.self_improvement_intelligence.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio.", _j + "risk_governor", _j + "permission",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "modify_strategy(", "modify_model(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.self_improvement_intelligence.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def trade", "def allocate", "def deploy", "def modify_strategy",
               "def modify_model", "def activate_live"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchSelfImprovementEngine))
    for banned in ("execute", "trade", "allocate", "deploy", "modify_strategy", "modify_model",
                   "activate_live", "apply_recommendation", "select_experiment", "place_order"):
        assert banned not in api


def test_suggestion_not_action(tmp_path, monkeypatch):
    """권고 레코드에 action/apply/deploy 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _rec(eng)
    d = r.to_dict()
    for banned in ("action", "apply", "deploy", "auto_fix"):
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
        m = importlib.import_module(f"jarvis.self_improvement_intelligence.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_si_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("si_")


def test_no_collision_with_sim_prefix():
    """si_ 원장이 P10.8 simulation 의 sim_ 및 타 레이어와 겹치지 않아야 한다."""
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"sim_scenarios.jsonl", "sim_results.jsonl", "sim_runs.jsonl",
             "rg_strategies.jsonl", "ai_signals.jsonl", "kg_entities.jsonl",
             "di_candidates.jsonl", "ci_variables.jsonl", "mi_patterns.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("si_") and not fn.startswith("sim_") for fn in ours)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, spec in ledger.SOURCE_LEDGERS.items():
        assert spec[0] not in owned


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 P10.2~P10.12 원장을 시드한 뒤 전체 워크플로를 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"rg_strategies.jsonl": [{"strategy_id": "ST1"}],
             "ai_experiments.jsonl": [{"experiment_id": "EX1"}],
             "ci_evidences.jsonl": [{"evidence_id": "CIE:1"}],
             "mi_patterns.jsonl": [{"event_id": "E1", "pattern_id": "MIP:1"}]}
    hashes = {}
    for fn, rows in seeds.items():
        with open(sp(fn), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    refs = eng.list_source_objects("research_governance")
    assert refs == ["research_governance:ST1"]
    _full(eng)
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_engine_only_appends_si_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("si_") for f in created)


def test_node_and_edge_types_defined():
    assert "WORKFLOW" in M.NODE_TYPES and "RECOMMENDATION" in M.NODE_TYPES
    assert set(M.EDGE_TYPES) == {"CAUSED_BY", "IMPROVES", "LEARNED_FROM", "DERIVED_FROM",
                                 "SUPPORTED_BY"}


def test_list_source_objects_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("NOPE") == []
