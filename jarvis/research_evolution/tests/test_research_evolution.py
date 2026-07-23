"""P10.16 Research Evolution Governance 테스트. **연구 결과→학습 기록 전환 저장·분석 전용.**

연구 객체(불변)·실패 패턴(불변·범주 검증)·진화 사이클 생명주기(CREATED→ANALYZED→LEARNING_CAPTURED→
ARCHIVED, 차단전이)·개선 제안 생명주기(DRAFT→REVIEWING→ACCEPTED→IMPLEMENTED→ARCHIVED, IMPLEMENTED=
연구 상태 기록)·이터레이션·학습 기록(불변)·지식 이전(불변)·계보(dangling/순환)·리포트·verify(체인/변조/
중복/전이/계보)·replay·상위 READ ONLY 보호·CLI·보안(금지import·실행/거래/배포/수정/배분 없음·상위 원장
무변경·삭제 API 없음·불변·LEARNING≠MODIFICATION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_evolution import ledger
from jarvis.research_evolution import models as M
from jarvis.research_evolution.engine import ResearchEvolutionEngine
from jarvis.research_evolution.models import (
    ACCEPTED,
    ANALYZED,
    ARCHIVED,
    CREATED,
    DRAFT,
    IMPLEMENTED,
    LEARNING_CAPTURED,
    REVIEWING,
    IllegalTransition,
    ImmutableFailureError,
    ImmutableLearningError,
    ImmutableResearchObjectError,
    ImmutableTransferError,
    InvalidFailureCategory,
    UnknownCycle,
    UnknownProposal,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"evidence_strength": 0.9, "reproducibility": 0.85, "applicability_breadth": 0.8,
       "confidence": 0.9, "future_value": 0.8}
_LO = {"evidence_strength": 0.1, "reproducibility": 0.1, "applicability_breadth": 0.2,
       "confidence": 0.2, "future_value": 0.1}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_evolution.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchEvolutionEngine()


def _obj(eng, layer="research_governance", ref="rg:ST1", rtype=M.RT_STRATEGY, meta=None,
         commit=True):
    return eng.register_research_object(layer, ref, rtype, meta or {}, T0, commit=commit)


def _fail(eng, cat=None, pattern="oos sharpe collapse", sev="HIGH", ev=None, rel=None, freq=2,
          commit=True):
    return eng.record_failure(cat or M.F_OVERFITTING, pattern, sev, ev or ["e1"], rel or [], freq,
                              T0, commit=commit)


def _cycle(eng, name="ST1_evo", sources=None, commit=True):
    return eng.create_evolution_cycle(name, sources or ["research_governance:rg:ST1"],
                                      ["obs1"], ["lesson1"], ["q1?"], T0, commit=commit)


def _prop(eng, fail_ref=None, hyp="add turnover penalty", commit=True):
    return eng.create_improvement_proposal(fail_ref or "EFP:xyz", hyp, "lower turnover", ["ev1"],
                                           T0, commit=commit)


def _learn(eng, source="EFP:xyz", lesson="regularize params", conf=0.7, ap=M.AP_BROAD,
           commit=True):
    return eng.create_learning_record(source, lesson, conf, ap, [], T0, commit=commit)


def _transfer(eng, frm="ST1", to="ST2", knowledge="turnover control", commit=True):
    return eng.create_transfer_record(frm, to, knowledge, M.AP_MODERATE, [], T0, commit=commit)


def _full(eng):
    """object→failure→proposal→learning→cycle→iteration→transfer→report end-to-end."""
    o = _obj(eng)
    f = _fail(eng, rel=[o.object_id])
    p = _prop(eng, f.failure_id)
    l = _learn(eng, source=f.failure_id)
    c = _cycle(eng)
    eng.record_iteration(c.cycle_id, 1, ["tweak"], M.OUTCOME_PARTIAL, "n", T0, commit=True)
    _transfer(eng, knowledge="from " + l.learning_id)
    eng.generate_report("GLOBAL", _HI, T1, commit=True)
    return o, f, p, l, c


# ── Research Object ──
def test_register_object_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _obj(_eng())
    assert o.object_id.startswith("ERO:")
    assert o.source_layer == "research_governance"
    assert o.research_type == M.RT_STRATEGY


def test_object_persisted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _obj(_eng())
    assert len(ledger.read_research_objects()) == 1


def test_object_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _obj(_eng(), commit=False)
    assert ledger.read_research_objects() == []


def test_object_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _obj(_eng())
    b = M.research_object_id("research_governance", "rg:ST1")
    assert a.object_id == b


def test_object_idempotent_same_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _obj(eng, meta={"k": 1})
    b = _obj(eng, meta={"k": 1})
    assert a.object_id == b.object_id
    assert len(ledger.read_research_objects()) == 1


def test_object_immutable_different_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _obj(eng, meta={"k": 1})
    with pytest.raises(ImmutableResearchObjectError):
        _obj(eng, meta={"k": 2})


def test_object_has_record_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _obj(_eng())
    assert o.record_hash.startswith("sha256:")


def test_object_metadata_hash_stable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _obj(_eng(), meta={"a": 1, "b": 2})
    assert o.metadata_hash == M.metadata_hash({"research_type": M.RT_STRATEGY,
                                               "metadata": {"a": 1, "b": 2}})


def test_object_all_research_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, rt in enumerate(M.RESEARCH_TYPES):
        o = _obj(eng, ref=f"ref{i}", rtype=rt)
        assert o.research_type == rt
    assert len(ledger.read_research_objects()) == len(M.RESEARCH_TYPES)


def test_object_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _obj(_eng())
    aid = M.artifact_id(M.ART_OBJECT, o.object_id)
    assert ledger.artifact_exists(aid)


def test_get_research_object(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _obj(_eng())
    assert ledger.get_research_object(o.object_id)["object_id"] == o.object_id


# ── Failure Pattern ──
def test_record_failure_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _fail(_eng())
    assert f.failure_id.startswith("EFP:")
    assert f.category == M.F_OVERFITTING
    assert f.frequency == 2


def test_failure_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidFailureCategory):
        _eng().record_failure("not_a_category", "x", "LOW", [], [], 1, T0, commit=True)


def test_failure_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, cat in enumerate(M.FAILURE_CATEGORIES):
        f = eng.record_failure(cat, f"pattern{i}", "MEDIUM", [], [], 1, T0, commit=True)
        assert f.category == cat
    assert len(ledger.read_failures()) == len(M.FAILURE_CATEGORIES)


def test_failure_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _fail(eng)
    b = _fail(eng)
    assert a.failure_id == b.failure_id
    assert len(ledger.read_failures()) == 1


def test_failure_immutable_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fail(eng, freq=2)
    with pytest.raises(ImmutableFailureError):
        _fail(eng, freq=9)


def test_failure_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _fail(_eng())
    assert f.failure_id == M.failure_id(M.F_OVERFITTING, "oos sharpe collapse")


def test_failure_related_objects_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _fail(_eng(), rel=["ERO:aaa", "ERO:bbb"])
    assert f.related_objects == ["ERO:aaa", "ERO:bbb"]


def test_failure_parent_links_object(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _obj(eng)
    f = _fail(eng, rel=[o.object_id])
    fa = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == f.failure_id and a["artifact_type"] == M.ART_FAILURE)
    assert fa["parent_artifact"] == M.artifact_id(M.ART_OBJECT, o.object_id)


def test_failure_severity_weight():
    assert M.severity_weight("CRITICAL") == 1.0
    assert M.severity_weight("LOW") == 0.25
    assert M.severity_weight("???") == 0.0


# ── Evolution Cycle lifecycle ──
def test_cycle_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _cycle(_eng())
    assert c.cycle_id.startswith("EVC:")
    assert c.to_state == CREATED


def test_cycle_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    assert eng.cycle_state(c.cycle_id) == CREATED


def test_cycle_advance(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    eng.advance_cycle(c.cycle_id, T1, commit=True)
    assert eng.cycle_state(c.cycle_id) == ANALYZED
    eng.advance_cycle(c.cycle_id, T2, commit=True)
    assert eng.cycle_state(c.cycle_id) == LEARNING_CAPTURED


def test_cycle_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    for _ in range(4):
        eng.advance_cycle(c.cycle_id, T1, commit=True)
    assert eng.cycle_state(c.cycle_id) == ARCHIVED


def test_cycle_transition_explicit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    eng.transition_cycle(c.cycle_id, ANALYZED, T1, commit=True)
    assert eng.cycle_state(c.cycle_id) == ANALYZED


def test_cycle_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_cycle(c.cycle_id, LEARNING_CAPTURED, T1, commit=True)


def test_cycle_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownCycle):
        _eng().transition_cycle("EVC:nope", ANALYZED, T1, commit=True)


def test_cycle_idempotent_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cycle(eng)
    b = _cycle(eng)
    assert a.cycle_id == b.cycle_id
    assert len(ledger.distinct_cycles()) == 1


def test_cycle_keeps_future_questions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _cycle(_eng())
    assert c.future_questions == ["q1?"]
    assert c.lessons == ["lesson1"]


def test_cycle_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    for _ in range(4):
        eng.advance_cycle(c.cycle_id, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_cycle(c.cycle_id, CREATED, T1, commit=True)


def test_can_transition_cycle_table():
    assert M.can_transition_cycle("", CREATED)
    assert M.can_transition_cycle(CREATED, ANALYZED)
    assert not M.can_transition_cycle(CREATED, ARCHIVED)
    assert not M.can_transition_cycle(ARCHIVED, CREATED)


# ── Iteration ──
def test_iteration_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    it = eng.record_iteration(c.cycle_id, 1, ["c1"], M.OUTCOME_SUCCESS, "note", T0, commit=True)
    assert it.iteration_id.startswith("EIT:")
    assert it.outcome == M.OUTCOME_SUCCESS
    assert it.iteration_number == 1


def test_iteration_persisted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    eng.record_iteration(c.cycle_id, 1, [], "PARTIAL", "", T0, commit=True)
    eng.record_iteration(c.cycle_id, 2, [], "SUCCESS", "", T0, commit=True)
    assert len(ledger.iterations_for(c.cycle_id)) == 2


def test_iteration_parent_links_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    it = eng.record_iteration(c.cycle_id, 1, [], "PARTIAL", "", T0, commit=True)
    ia = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == it.iteration_id and a["artifact_type"] == M.ART_ITERATION)
    assert ia["parent_artifact"] == M.artifact_id(M.ART_CYCLE, c.cycle_id)


def test_iteration_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    it = eng.record_iteration(c.cycle_id, 3, [], "PARTIAL", "", T0, commit=True)
    assert it.iteration_id == M.iteration_id(c.cycle_id, 3)


# ── Improvement Proposal lifecycle ──
def test_proposal_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _prop(_eng())
    assert p.proposal_id.startswith("EIP:")
    assert p.to_state == DRAFT


def test_proposal_accept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _prop(eng)
    eng.accept_proposal(p.proposal_id, T1, commit=True)
    assert eng.proposal_state(p.proposal_id) == ACCEPTED


def test_proposal_implemented_is_record_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _prop(eng)
    eng.accept_proposal(p.proposal_id, T1, commit=True)
    res = eng.mark_proposal_implemented(p.proposal_id, T2, commit=True)
    assert eng.proposal_state(p.proposal_id) == IMPLEMENTED
    assert "프로덕션 변경" in res["note"]


def test_proposal_implement_requires_accepted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _prop(eng)
    with pytest.raises(IllegalTransition):
        eng.mark_proposal_implemented(p.proposal_id, T1, commit=True)


def test_proposal_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _prop(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_proposal(p.proposal_id, IMPLEMENTED, T1, commit=True)


def test_proposal_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownProposal):
        _eng().transition_proposal("EIP:nope", REVIEWING, T1, commit=True)


def test_proposal_draft_to_archived(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _prop(eng)
    eng.transition_proposal(p.proposal_id, ARCHIVED, T1, commit=True)
    assert eng.proposal_state(p.proposal_id) == ARCHIVED


def test_proposal_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _prop(eng)
    b = _prop(eng)
    assert a.proposal_id == b.proposal_id
    assert len(ledger.distinct_proposals()) == 1


def test_proposal_parent_links_failure(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    f = _fail(eng)
    p = _prop(eng, f.failure_id)
    pa = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == p.proposal_id and a["artifact_type"] == M.ART_PROPOSAL)
    assert pa["parent_artifact"] == M.artifact_id(M.ART_FAILURE, f.failure_id)


def test_proposal_full_chain_states(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _prop(eng)
    eng.transition_proposal(p.proposal_id, REVIEWING, T1, commit=True)
    eng.transition_proposal(p.proposal_id, ACCEPTED, T1, commit=True)
    eng.transition_proposal(p.proposal_id, IMPLEMENTED, T2, commit=True)
    eng.transition_proposal(p.proposal_id, ARCHIVED, T2, commit=True)
    assert eng.proposal_state(p.proposal_id) == ARCHIVED


def test_can_transition_proposal_table():
    assert M.can_transition_proposal("", DRAFT)
    assert M.can_transition_proposal(ACCEPTED, IMPLEMENTED)
    assert not M.can_transition_proposal(DRAFT, IMPLEMENTED)
    assert not M.can_transition_proposal(IMPLEMENTED, ACCEPTED)


# ── Learning Record ──
def test_learning_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _learn(_eng())
    assert l.learning_id.startswith("ELR:")
    assert l.applicability == M.AP_BROAD
    assert l.confidence == 0.7


def test_learning_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _learn(eng)
    b = _learn(eng)
    assert a.learning_id == b.learning_id
    assert len(ledger.read_learning()) == 1


def test_learning_immutable_confidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _learn(eng, conf=0.7)
    with pytest.raises(ImmutableLearningError):
        _learn(eng, conf=0.9)


def test_learning_immutable_applicability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _learn(eng, ap=M.AP_BROAD)
    with pytest.raises(ImmutableLearningError):
        _learn(eng, ap=M.AP_NARROW)


def test_learning_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _learn(_eng())
    assert l.learning_id == M.learning_id("EFP:xyz", "regularize params")


def test_learning_parent_links_failure(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    f = _fail(eng)
    l = _learn(eng, source=f.failure_id)
    la = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == l.learning_id and a["artifact_type"] == M.ART_LEARNING)
    assert la["parent_artifact"] == M.artifact_id(M.ART_FAILURE, f.failure_id)


def test_learning_lineage_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _eng().create_learning_record("s", "lesson", 0.5, M.AP_MODERATE, ["a", "b"], T0,
                                      commit=True)
    assert l.lineage == ["a", "b"]


# ── Knowledge Transfer ──
def test_transfer_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _transfer(_eng())
    assert t.transfer_id.startswith("EKT:")
    assert t.from_context == "ST1"
    assert t.to_context == "ST2"


def test_transfer_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _transfer(eng)
    b = _transfer(eng)
    assert a.transfer_id == b.transfer_id
    assert len(ledger.read_transfers()) == 1


def test_transfer_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _transfer(eng)
    with pytest.raises(ImmutableTransferError):
        eng.create_transfer_record("ST1", "ST2", "turnover control", M.AP_BROAD, [], T0,
                                   commit=True)


def test_transfer_parent_links_learning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _learn(eng)
    t = eng.create_transfer_record("c1", "c2", "k", M.AP_MODERATE, [l.learning_id], T0,
                                   commit=True)
    ta = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == t.transfer_id and a["artifact_type"] == M.ART_TRANSFER)
    assert ta["parent_artifact"] == M.artifact_id(M.ART_LEARNING, l.learning_id)


def test_transfer_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _transfer(_eng())
    assert t.transfer_id == M.transfer_id("ST1", "ST2", "turnover control")


# ── Learning score / analyze ──
def test_learning_score_high():
    assert M.learning_score(_HI) > 0.7


def test_learning_score_low():
    assert M.learning_score(_LO) < 0.4


def test_learning_score_range():
    assert 0.0 <= M.learning_score(_HI) <= 1.0


def test_learning_score_empty_zero():
    assert M.learning_score({}) == 0.0


def test_learning_weights_sum_one():
    assert abs(sum(M.LEARNING_WEIGHTS.values()) - 1.0) < 1e-9


def test_learning_confidence_labels():
    assert M.learning_confidence(_HI) == "HIGH"
    assert M.learning_confidence(_LO) == "LOW"
    assert M.learning_confidence({"evidence_strength": 1.0, "reproducibility": 1.0}) == "MEDIUM"


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HI)
    assert res["learning_confidence"] == "HIGH"
    assert res["learning_score"] > 0.7


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.report_id.startswith("ERP:")
    assert r.object_count >= 1
    assert r.failure_count >= 1
    assert r.learning_count >= 1


def test_report_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert M.RT_STRATEGY in r.research_type_distribution
    assert M.F_OVERFITTING in r.failure_category_distribution


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert "LEARNING ≠ MODIFICATION" in r.disclaimer


def test_report_learning_confidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert r.learning_confidence == "HIGH"


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    d = r.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d, ensure_ascii=False).lower()
    for verb in ("buy", "sell", "place_order", "deploy", "allocate_capital"):
        assert verb not in blob


# ── Lineage verify (engine) ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _obj(eng)
    f = _fail(eng, rel=[o.object_id])
    l = _learn(eng, source=f.failure_id)
    anc = eng.trace_lineage(M.artifact_id(M.ART_LEARNING, l.learning_id))
    assert M.artifact_id(M.ART_FAILURE, f.failure_id) in anc
    assert M.artifact_id(M.ART_OBJECT, o.object_id) in anc


def test_verify_lineage_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _obj(eng)
    # inject a broken artifact with missing parent
    from jarvis.research_evolution.models import content_hash
    rec = {"artifact_id": "EVA:broken", "artifact_type": "LEARNING", "ref_id": "x",
           "parent_artifact": "EVA:ghost", "created_at": T0, "input_hash": "", "record_hash": "",
           "previous_hash": ledger.artifacts_head()["record_hash"]}
    rec["record_hash"] = content_hash(rec)
    ledger.append_artifact(rec)
    assert eng.verify_lineage()["ok"] is False


# ── verify_chain ──
def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_evolution.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _obj(eng)
    p = sp("ev_research_objects.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["source_reference"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_evolution.verify import verify_ledger
    assert verify_ledger(ledger.RESEARCH_OBJECTS)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fail(eng, pattern="p1")
    _fail(eng, pattern="p2")
    p = sp("ev_failures.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_evolution.verify import verify_ledger
    assert verify_ledger(ledger.FAILURES)["ok"] is False


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_cycle_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    eng.advance_cycle(c.cycle_id, T1, commit=True)
    from jarvis.research_evolution.verify import cycle_transition_validation
    assert cycle_transition_validation()["ok"] is True


def test_verify_proposal_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _prop(eng)
    eng.accept_proposal(p.proposal_id, T1, commit=True)
    from jarvis.research_evolution.verify import proposal_transition_validation
    assert proposal_transition_validation()["ok"] is True


def test_verify_detects_bad_transition(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    p = sp("ev_evolution_cycles.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["to_state"] = "LEARNING_CAPTURED"  # illegal from GENESIS
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_evolution.verify import cycle_transition_validation
    assert cycle_transition_validation()["ok"] is False


# ── replay / determinism ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_evolution.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert s.object_count >= 1
    assert s.failure_count >= 1
    assert s.proposal_count >= 1
    assert s.learning_count >= 1
    assert s.transfer_count >= 1
    assert s.iteration_count >= 1


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


def test_source_ledgers_read_only_no_write(tmp_path, monkeypatch):
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


# ── CLI ──
def test_cli_object(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    rc = main(["object", "--source-layer", "research_governance", "--source-reference", "rg:ST1",
               "--research-type", "STRATEGY", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["object"]["object_id"].startswith("ERO:")


def test_cli_failure(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    rc = main(["failure", "--category", "overfitting", "--pattern", "collapse", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["failure"]["failure_id"].startswith("EFP:")


def test_cli_cycle(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    rc = main(["cycle", "--name", "evo1", "--lessons", "l1,l2", "--questions", "q1", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["cycle"]["cycle_id"].startswith("EVC:")


def test_cli_proposal(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    rc = main(["proposal", "--source-failure", "EFP:x", "--hypothesis", "penalize", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["proposal"]["proposal_id"].startswith("EIP:")


def test_cli_learning(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    rc = main(["learning", "--source", "EFP:x", "--lesson", "regularize", "--confidence", "0.7",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["learning"]["learning_id"].startswith("ELR:")


def test_cli_transfer(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    rc = main(["transfer", "--from-context", "A", "--to-context", "B", "--knowledge", "k",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["transfer"]["transfer_id"].startswith("EKT:")


def test_cli_iteration(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    main(["cycle", "--name", "evo1", "--commit"])
    cid = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    rc = main(["iteration", "--cycle-ref", cid, "--number", "1", "--outcome", "PARTIAL",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["iteration"]["iteration_id"].startswith("EIT:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    rc = main(["report", "--metrics-json", json.dumps(_HI), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("ERP:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    main(["failure", "--category", "overfitting", "--pattern", "p", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    main(["object", "--source-layer", "x", "--source-reference", "y", "--research-type",
          "STRATEGY", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_evolution.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "object_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_evolution.engine as eng_mod
    import jarvis.research_evolution.models as mdl_mod
    import jarvis.research_evolution.ledger as led_mod
    import jarvis.research_evolution.verify as ver_mod
    import jarvis.research_evolution.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "activate_live(", "modify_strategy(", "auto_improve(",
                 "auto_update("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.research_evolution.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def trade", "def deploy", "def place_order",
               "def allocate_capital", "def activate_live", "def modify_strategy",
               "def auto_improve", "def auto_update"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchEvolutionEngine))
    for banned in ("execute", "trade", "deploy", "place_order", "allocate_capital",
                   "activate_live", "modify_strategy", "auto_improve", "auto_update"):
        assert banned not in api


def test_learning_not_modification(tmp_path, monkeypatch):
    """학습 기록에 modify/deploy/apply/execute 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    l = _learn(_eng())
    d = l.to_dict()
    for banned in ("modify", "deploy", "apply", "execute", "action"):
        assert banned not in d


def test_proposal_not_approval(tmp_path, monkeypatch):
    """제안 레코드에 approve/deploy/execute 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    p = _prop(_eng())
    d = p.to_dict()
    for banned in ("approve", "deploy", "execute", "auto_apply"):
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
        m = importlib.import_module(f"jarvis.research_evolution.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_ev(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("ev_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 9


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.research_object_id("a", "b")[:4],
        M.cycle_id("a")[:4],
        M.cycle_event_id("a", "", CREATED)[:4],
        M.proposal_id("a", "b")[:4],
        M.proposal_event_id("a", "", DRAFT)[:4],
        M.failure_id("a", "b")[:4],
        M.iteration_id("a", 1)[:4],
        M.learning_id("a", "b")[:4],
        M.transfer_id("a", "b", "c")[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 11


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_metadata_hash_order_independent():
    assert M.metadata_hash({"a": 1, "b": 2}) == M.metadata_hash({"b": 2, "a": 1})


def test_severities_defined():
    assert set(M.SEVERITIES) == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_outcomes_defined():
    assert M.OUTCOME_SUCCESS in M.OUTCOMES
    assert M.OUTCOME_FAILURE in M.OUTCOMES


def test_applicabilities_defined():
    assert set(M.APPLICABILITIES) == {"NARROW", "MODERATE", "BROAD"}


def test_node_types_count():
    assert len(M.NODE_TYPES) == 7


def test_edge_types_count():
    assert len(M.EDGE_TYPES) == 5


def test_failure_categories_count():
    assert len(M.FAILURE_CATEGORIES) == 8


def test_research_types_count():
    assert len(M.RESEARCH_TYPES) == 8


def test_object_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _obj(_eng())
    d = o.to_dict()
    assert d["object_id"] == o.object_id
    assert set(("source_layer", "source_reference", "research_type")).issubset(d)


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("GLOBAL", _HI, T0, commit=True)
    eng.generate_report("GLOBAL", _HI, T0, commit=True)
    assert len(ledger.read_reports()) == 1


def test_multiple_scopes_distinct_reports(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("A", _HI, T0, commit=True)
    eng.generate_report("B", _HI, T0, commit=True)
    assert len(ledger.read_reports()) == 2


def test_full_workflow_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_evolution.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["cycle_transitions"]["ok"] is True
    assert res["proposal_transitions"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_artifact_chain_hashes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_evolution.verify import verify_ledger
    assert verify_ledger(ledger.ARTIFACTS)["ok"] is True


def test_learning_confidence_boundary():
    # evidence_strength weight = 0.30 → score 0.30 → below 0.4 → LOW
    assert M.learning_score({"evidence_strength": 1.0}) == 0.3
    assert M.learning_confidence({"evidence_strength": 1.0}) == "LOW"


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    for phrase in ("LEARNING ≠ MODIFICATION", "PROPOSAL ≠ APPROVAL", "ACCEPTED ≠ DEPLOYMENT",
                   "IMPLEMENTED(record) ≠ PRODUCTION CHANGE"):
        assert phrase in r.disclaimer


def test_engine_import_no_upstream_layer():
    """엔진은 상위 인텔리전스 레이어를 import 하지 않는다(파일만 읽음)."""
    import jarvis.research_evolution.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.meta_intelligence", "import jarvis.self_improvement",
               "import jarvis.research_planning", "import jarvis.research_memory"):
        assert up not in src


def test_proposal_evidence_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _prop(_eng())
    assert p.evidence == ["ev1"]
    assert p.expected_improvement == "lower turnover"


def test_failure_evidence_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _fail(_eng())
    assert f.evidence == ["e1"]


def test_cycle_source_objects_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _cycle(_eng())
    assert c.source_objects == ["research_governance:rg:ST1"]


def test_report_proposal_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _prop(eng)
    eng.accept_proposal(p.proposal_id, T1, commit=True)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.proposal_state_distribution.get(ACCEPTED) == 1


def test_report_cycle_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    eng.advance_cycle(c.cycle_id, T1, commit=True)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.cycle_state_distribution.get(ANALYZED) == 1


def test_summary_state_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert CREATED in s.cycle_state_distribution
    assert DRAFT in s.proposal_state_distribution


def test_object_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _obj(_eng())
    assert o.input_hash == M.input_digest("research_governance", "rg:ST1")


def test_iteration_outcomes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cycle(eng)
    for i, oc in enumerate(M.OUTCOMES):
        it = eng.record_iteration(c.cycle_id, i, [], oc, "", T0, commit=True)
        assert it.outcome == oc


def test_transfer_supporting_learning_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _eng().create_transfer_record("a", "b", "k", M.AP_BROAD, ["ELR:1", "ELR:2"], T0,
                                      commit=True)
    assert t.supporting_learning == ["ELR:1", "ELR:2"]


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _obj(eng, commit=False)
    _fail(eng, commit=False)
    _learn(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_source_ledgers_all_read_only_names():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("ev_")
        assert isinstance(idf, str)


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _obj(eng)
    from jarvis.research_evolution.models import content_hash
    # two artifacts pointing at each other
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "EVA:c1", "artifact_type": "LEARNING", "ref_id": "x1",
          "parent_artifact": "EVA:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "EVA:c2", "artifact_type": "LEARNING", "ref_id": "x2",
          "parent_artifact": "EVA:c1", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": a1["record_hash"]}
    a2["record_hash"] = content_hash(a2)
    ledger.append_artifact(a2)
    res = eng.verify_lineage()
    assert res["ok"] is False
    assert any("cycle" in i for i in res["issues"])


def test_engine_reused_across_calls(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o1 = _obj(eng, ref="r1")
    o2 = _obj(eng, ref="r2")
    assert o1.object_id != o2.object_id
    assert len(ledger.read_research_objects()) == 2


def test_report_metrics_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert r.metrics == _HI


def test_learning_score_partial_metrics():
    s = M.learning_score({"evidence_strength": 1.0, "confidence": 1.0})
    assert abs(s - (0.30 + 0.15)) < 1e-9
