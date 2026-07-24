"""P12.1 Autonomous Research Pipeline Core 테스트. **파이프라인 오케스트레이션 전용.**

목표 인테이크·사이클 초기화(OBJECTIVE_CREATED→…→COMPLETED 9단계)·파이프라인 런·스테이지 전이(스킵/역행/무단완료
차단)·연구 참조 부착(상태 모델)·결과 수집·리뷰 라우팅·사이클 완료·아티팩트 계보·스냅샷/리포트(is_binding=False)·
verify(체인/변조/중복/전이/아티팩트누락/고아사이클/참조/계보)·replay·CLI·보안(금지import·실행/배포/승인 없음·삭제 API
없음·불변·PIPELINE≠EXECUTION·append-only·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.autonomous_research_pipeline import ledger
from jarvis.autonomous_research_pipeline import models as M
from jarvis.autonomous_research_pipeline.engine import AutonomousResearchPipelineEngine
from jarvis.autonomous_research_pipeline.models import (
    CYCLE_STAGES,
    REF_TYPES,
    S_COMPLETED,
    S_EXPERIMENT_DESIGN,
    S_EXPERIMENT_RUNNING,
    S_HYPOTHESIS_FORMING,
    S_KNOWLEDGE_UPDATE,
    S_OBJECTIVE_CREATED,
    S_PLANNING,
    S_RESULT_ANALYSIS,
    S_REVIEW_PENDING,
    DanglingReferenceError,
    IllegalStageTransition,
    ImmutableCycleError,
    ImmutableObjectiveError,
    ImmutablePipelineError,
    ImmutableRunError,
    InvalidReferenceType,
    UnknownCycleError,
    UnknownObjectiveError,
    UnknownPipelineError,
)
from jarvis.autonomous_research_pipeline.verify import (
    artifact_presence,
    cycle_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    transition_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]

_STAGE_SEQ = [S_PLANNING, S_HYPOTHESIS_FORMING, S_EXPERIMENT_DESIGN, S_EXPERIMENT_RUNNING,
              S_RESULT_ANALYSIS, S_REVIEW_PENDING, S_KNOWLEDGE_UPDATE, S_COMPLETED]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.autonomous_research_pipeline.ledger.state_path", sp)
    return sp


def _eng():
    return AutonomousResearchPipelineEngine()


def _pipeline(e, name="alpha_pipeline", now=T[0]):
    return e.register_pipeline(name, "autonomous research", now, commit=True).pipeline_id


def _objective(e, pl=None, title="improve momentum", now=T[1]):
    if pl is None:
        pl = _pipeline(e)
    return e.create_research_objective(pl, title, "desc", "sharpe", "", now, commit=True).objective_id


def _cycle(e, obj=None, now=T[2]):
    if obj is None:
        obj = _objective(e)
    return e.initialize_cycle(obj, 1, now, commit=True).cycle_id


def _advance_to(e, cycle, target, start_t=3):
    """cycle 을 target 스테이지까지 선형 전이."""
    for i, st in enumerate(_STAGE_SEQ):
        e.advance_stage(cycle, st, "", T[start_t + i], commit=True)
        if st == target:
            break
    return cycle


# ══════════════ Phase 0 / 접두사 / 소유 ══════════════
def test_prefix_all_ledgers_arp():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("arp_")


def test_nine_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 9


def test_source_ledgers_count():
    assert len(ledger.SOURCE_LEDGERS) == 23
    assert "research_organization" in ledger.SOURCE_LEDGERS
    assert "data_governance" in ledger.SOURCE_LEDGERS


def test_nine_cycle_stages():
    assert len(CYCLE_STAGES) == 9


def test_eight_ref_types():
    assert len(REF_TYPES) == 8


def test_seven_pipeline_components():
    assert len(M.PIPELINE_COMPONENTS) == 7


# ══════════════ register_pipeline ══════════════
def test_register_pipeline_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_pipeline("p", "m", T[0], commit=True)
    b = e.register_pipeline("p", "m", T[1], commit=False)
    assert a.pipeline_id == b.pipeline_id
    assert a.pipeline_id.startswith("APG:")


def test_register_pipeline_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_pipeline("p", "m", T[0], commit=True)
    e.register_pipeline("p", "m", T[1], commit=True)
    assert len(ledger.read_pipelines()) == 1


def test_register_pipeline_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_pipeline("p", "m1", T[0], commit=True)
    with pytest.raises(ImmutablePipelineError):
        e.register_pipeline("p", "m2", T[1], commit=True)


# ══════════════ create_research_objective (objective lifecycle) ══════════════
def test_create_objective_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    obj = _objective(e)
    assert obj.startswith("APO:")


def test_create_objective_requires_pipeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownPipelineError):
        e.create_research_objective("APG:ghost", "t", now=T[1], commit=True)


def test_create_objective_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pl = _pipeline(e)
    e.create_research_objective(pl, "t", "d1", now=T[1], commit=True)
    with pytest.raises(ImmutableObjectiveError):
        e.create_research_objective(pl, "t", "d2", now=T[2], commit=True)


def test_create_objective_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    obj = _objective(e)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_OBJECTIVE]
    assert any(a["ref_id"] == obj for a in arts)


def test_create_objective_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pl = _pipeline(e)
    e.create_research_objective(pl, "t", now=T[1], commit=False)
    assert ledger.read_objectives() == []


# ══════════════ initialize_cycle ══════════════
def test_initialize_cycle_genesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    assert cyc.startswith("APC:")
    assert e.current_stage(cyc) == S_OBJECTIVE_CREATED


def test_initialize_cycle_requires_objective(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownObjectiveError):
        e.initialize_cycle("APO:ghost", 1, T[2], commit=True)


def test_initialize_cycle_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    obj = _objective(e)
    e.initialize_cycle(obj, 1, T[2], commit=True)
    e.initialize_cycle(obj, 1, T[3], commit=True)
    assert len(ledger.read_cycles()) == 1


def test_initialize_cycle_iterations_distinct(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    obj = _objective(e)
    c1 = e.initialize_cycle(obj, 1, T[2], commit=True).cycle_id
    c2 = e.initialize_cycle(obj, 2, T[3], commit=True).cycle_id
    assert c1 != c2


def test_initialize_cycle_creates_genesis_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    trs = ledger.cycle_transitions(cyc)
    assert trs[0]["from_stage"] == M.GENESIS
    assert trs[0]["to_stage"] == S_OBJECTIVE_CREATED


def test_initialize_cycle_creates_artifact_with_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    obj = _objective(e)
    cyc = e.initialize_cycle(obj, 1, T[2], commit=True).cycle_id
    art = [a for a in ledger.read_artifacts()
           if a["artifact_type"] == M.ART_CYCLE and a["ref_id"] == cyc][0]
    assert art["parent_artifact"] == M.artifact_id(M.ART_OBJECTIVE, obj)


# ══════════════ create_pipeline_run ══════════════
def test_create_run_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    r = e.create_pipeline_run(cyc, "run1", "note", T[3], commit=True)
    assert r.run_id.startswith("APR:")


def test_create_run_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.create_pipeline_run(cyc, "run1", "n1", T[3], commit=True)
    with pytest.raises(ImmutableRunError):
        e.create_pipeline_run(cyc, "run1", "n2", T[4], commit=True)


def test_create_run_unknown_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownCycleError):
        e.create_pipeline_run("APC:ghost", "r", "", T[3], commit=True)


# ══════════════ advance_stage (valid linear) ══════════════
def test_advance_planning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.advance_stage(cyc, S_PLANNING, "", T[3], commit=True)
    assert e.current_stage(cyc) == S_PLANNING


def test_advance_full_linear_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_COMPLETED)
    assert e.current_stage(cyc) == S_COMPLETED
    assert e.stage_history(cyc) == list(CYCLE_STAGES)


def test_advance_creates_stage_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.advance_stage(cyc, S_PLANNING, "", T[3], commit=True)
    stages = [s["stage"] for s in ledger.cycle_stages(cyc)]
    assert S_PLANNING in stages


def test_advance_unknown_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownCycleError):
        e.advance_stage("APC:ghost", S_PLANNING, "", T[3], commit=True)


# ══════════════ invalid transition blocking ══════════════
def test_block_skip_stage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    # OBJECTIVE_CREATED → EXPERIMENT_RUNNING (스킵) 거부
    with pytest.raises(IllegalStageTransition):
        e.advance_stage(cyc, S_EXPERIMENT_RUNNING, "", T[3], commit=True)


def test_block_reverse_stage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_RESULT_ANALYSIS)
    with pytest.raises(IllegalStageTransition):
        e.advance_stage(cyc, S_PLANNING, "", T[20], commit=True)


def test_block_unauthorized_completion(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_PLANNING)
    # PLANNING → COMPLETED (무단 완료) 거부
    with pytest.raises(IllegalStageTransition):
        e.advance_stage(cyc, S_COMPLETED, "", T[20], commit=True)


def test_block_self_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(IllegalStageTransition):
        e.advance_stage(cyc, S_OBJECTIVE_CREATED, "", T[3], commit=True)


def test_complete_from_completed_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_COMPLETED)
    with pytest.raises(IllegalStageTransition):
        e.advance_stage(cyc, S_COMPLETED, "", T[30], commit=True)


@pytest.mark.parametrize("bad_to", [S_EXPERIMENT_DESIGN, S_RESULT_ANALYSIS, S_COMPLETED,
                                    S_KNOWLEDGE_UPDATE])
def test_block_various_skips_from_genesis(tmp_path, monkeypatch, bad_to):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(IllegalStageTransition):
        e.advance_stage(cyc, bad_to, "", T[3], commit=True)


# ══════════════ attach_research_task (state model) ══════════════
def test_attach_reference_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    h = e.attach_research_task(cyc, "experiment", "EXP1", "", T[3], commit=True)
    assert h.history_id.startswith("APH:")
    assert h.ref_type == "experiment"


def test_attach_invalid_ref_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(InvalidReferenceType):
        e.attach_research_task(cyc, "banana", "X", "", T[3], commit=True)


def test_attach_blocked_after_completion(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_COMPLETED)
    with pytest.raises(IllegalStageTransition):
        e.attach_research_task(cyc, "experiment", "EXP1", "", T[30], commit=True)


def test_state_model_agent_references(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.attach_research_task(cyc, "agent", "AG1", "", T[3], commit=True)
    e.attach_research_task(cyc, "agent", "AG2", "", T[4], commit=True)
    model = e.cycle_state_model(cyc)
    assert model["agent"] == ["AG1", "AG2"]


def test_state_model_experiment_references(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.attach_research_task(cyc, "experiment", "EXP1", "", T[3], commit=True)
    model = e.cycle_state_model(cyc)
    assert "EXP1" in model["experiment"]


def test_state_model_dataset_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.attach_research_task(cyc, "dataset", "DS1", "", T[3], commit=True)
    e.attach_research_task(cyc, "hypothesis", "H1", "", T[4], commit=True)
    e.attach_research_task(cyc, "memory", "MEM1", "", T[5], commit=True)
    model = e.cycle_state_model(cyc)
    assert model["dataset"] == ["DS1"]
    assert model["hypothesis"] == ["H1"]
    assert model["memory"] == ["MEM1"]


def test_state_model_includes_objective(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    obj = _objective(e)
    cyc = e.initialize_cycle(obj, 1, T[2], commit=True).cycle_id
    model = e.cycle_state_model(cyc)
    assert model["objective"] == [obj]


def test_state_model_all_ref_types_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    model = e.cycle_state_model(cyc)
    for t in REF_TYPES:
        assert t in model


@pytest.mark.parametrize("ref_type", list(REF_TYPES))
def test_attach_all_ref_types(tmp_path, monkeypatch, ref_type):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    h = e.attach_research_task(cyc, ref_type, "R-" + ref_type, "", T[3], commit=True)
    assert h.ref_type == ref_type


# ══════════════ collect_results ══════════════
def test_collect_results_in_running(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_EXPERIMENT_RUNNING)
    h = e.collect_results(cyc, "RES1", "sharpe 1.4", T[20], commit=True)
    assert h.kind == "RESULT"
    assert h.ref_id == "RES1"


def test_collect_results_in_analysis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_RESULT_ANALYSIS)
    h = e.collect_results(cyc, "RES1", "", T[20], commit=True)
    assert h.ref_id == "RES1"


def test_collect_results_blocked_early(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_PLANNING)
    with pytest.raises(IllegalStageTransition):
        e.collect_results(cyc, "RES1", "", T[20], commit=True)


def test_collect_results_in_state_model(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_RESULT_ANALYSIS)
    e.collect_results(cyc, "RES1", "", T[20], commit=True)
    model = e.cycle_state_model(cyc)
    assert "RES1" in model["result"]


# ══════════════ trigger_review_stage (review routing) ══════════════
def test_trigger_review_routes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_RESULT_ANALYSIS)
    e.trigger_review_stage(cyc, "REV1", T[20], commit=True)
    assert e.current_stage(cyc) == S_REVIEW_PENDING


def test_trigger_review_records_reference(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_RESULT_ANALYSIS)
    e.trigger_review_stage(cyc, "REV1", T[20], commit=True)
    model = e.cycle_state_model(cyc)
    assert "REV1" in model["review"]


def test_trigger_review_wrong_stage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_PLANNING)
    with pytest.raises(IllegalStageTransition):
        e.trigger_review_stage(cyc, "REV1", T[20], commit=True)


# ══════════════ complete_cycle ══════════════
def test_complete_cycle_success(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_KNOWLEDGE_UPDATE)
    e.complete_cycle(cyc, T[30], commit=True)
    assert e.current_stage(cyc) == S_COMPLETED


def test_complete_cycle_unauthorized(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_RESULT_ANALYSIS)
    with pytest.raises(IllegalStageTransition):
        e.complete_cycle(cyc, T[20], commit=True)


def test_cycles_in_stage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_PLANNING)
    assert cyc in e.cycles_in_stage(S_PLANNING)


# ══════════════ report ══════════════
def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pl = _pipeline(e)
    obj = e.create_research_objective(pl, "t", "d", "m", "", T[1], commit=True).objective_id
    cyc = e.initialize_cycle(obj, 1, T[2], commit=True).cycle_id
    _advance_to(e, cyc, S_COMPLETED)
    rep = e.generate_pipeline_report(pl, "PIPELINE", T[30], commit=True)
    assert rep.cycle_count == 1
    assert rep.completed_count == 1


def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pl = _pipeline(e)
    rep = e.generate_pipeline_report(pl, "PIPELINE", T[1], commit=True)
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pl = _pipeline(e)
    rep = e.generate_pipeline_report(pl, "PIPELINE", T[1], commit=True)
    assert "PIPELINE ≠ EXECUTION" in rep.disclaimer


def test_report_stage_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pl = _pipeline(e)
    obj = e.create_research_objective(pl, "t", "d", "m", "", T[1], commit=True).objective_id
    cyc = e.initialize_cycle(obj, 1, T[2], commit=True).cycle_id
    _advance_to(e, cyc, S_PLANNING)
    rep = e.generate_pipeline_report(pl, "PIPELINE", T[10], commit=True)
    assert rep.stage_distribution.get(S_PLANNING) == 1


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.create_pipeline_run(cyc, "r", "", T[3], commit=True)
    e.attach_research_task(cyc, "experiment", "EXP1", "", T[4], commit=True)
    _advance_to(e, cyc, S_COMPLETED, start_t=5)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cycle(e)
    p = ledger.state_path(ledger.CYCLES[0])
    recs = ledger.read_cycles()
    recs[0]["iteration"] = 999
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.advance_stage(cyc, S_PLANNING, "", T[3], commit=True)
    p = ledger.state_path(ledger.TRANSITIONS[0])
    recs = ledger.read_transitions()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.TRANSITIONS[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cycle(e)
    p = ledger.state_path(ledger.CYCLES[0])
    recs = ledger.read_cycles()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.CYCLES[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_transition_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_RESULT_ANALYSIS)
    assert transition_integrity()["ok"] is True


def test_transition_integrity_bad_initial(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng()
    p = ledger.state_path(ledger.TRANSITIONS[0])
    bad = {"transition_event_id": "APV:bad", "cycle_id": "APC:bad", "from_stage": M.GENESIS,
           "to_stage": S_PLANNING, "previous_hash": M.GENESIS}
    bad["record_hash"] = M.content_hash(bad)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps(bad, ensure_ascii=False) + "\n")
    assert transition_integrity()["ok"] is False


def test_cycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cycle(e)
    assert cycle_integrity()["ok"] is True


def test_cycle_integrity_orphan_objective(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    p = ledger.state_path(ledger.CYCLES[0])
    recs = ledger.read_cycles()
    recs[0]["objective_id"] = "APO:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert cycle_integrity()["ok"] is False


def test_cycle_integrity_duplicate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    p = ledger.state_path(ledger.CYCLES[0])
    recs = ledger.read_cycles()
    forged = dict(recs[0])
    forged["previous_hash"] = recs[0]["record_hash"]
    forged["record_hash"] = M.content_hash(forged)
    with open(p, "a") as f:
        f.write(json.dumps(forged, ensure_ascii=False, default=str) + "\n")
    assert cycle_integrity()["ok"] is False


def test_artifact_presence_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cycle(e)
    assert artifact_presence()["ok"] is True


def test_artifact_presence_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    # 아티팩트 원장에서 CYCLE 아티팩트 제거
    p = ledger.state_path(ledger.ARTIFACTS[0])
    recs = [a for a in ledger.read_artifacts()
            if not (a["artifact_type"] == M.ART_CYCLE and a["ref_id"] == cyc)]
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert artifact_presence()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.create_pipeline_run(cyc, "r", "", T[3], commit=True)
    assert reference_integrity()["ok"] is True


def test_reference_integrity_inconsistent_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.create_pipeline_run(cyc, "r", "", T[3], commit=True)
    p = ledger.state_path(ledger.RUNS[0])
    recs = ledger.read_runs()
    recs[0]["cycle_id"] = "APC:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert reference_integrity()["ok"] is False


def test_reference_integrity_corrupted_history(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.attach_research_task(cyc, "experiment", "EXP1", "", T[3], commit=True)
    p = ledger.state_path(ledger.HISTORY[0])
    recs = ledger.read_history()
    recs[0]["cycle_id"] = "APC:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert reference_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cycle(e)
    assert lineage_integrity()["ok"] is True


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cycle(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_PLANNING)
    s = e.summary(T[9])
    assert s.cycle_count == 1
    assert s.pipeline_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cycle(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cycle(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = verify_chain()
    assert res["ok"] is True and res["n"] == 0


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (S_OBJECTIVE_CREATED, S_PLANNING, True),
    (S_PLANNING, S_HYPOTHESIS_FORMING, True),
    (S_HYPOTHESIS_FORMING, S_EXPERIMENT_DESIGN, True),
    (S_EXPERIMENT_DESIGN, S_EXPERIMENT_RUNNING, True),
    (S_EXPERIMENT_RUNNING, S_RESULT_ANALYSIS, True),
    (S_RESULT_ANALYSIS, S_REVIEW_PENDING, True),
    (S_REVIEW_PENDING, S_KNOWLEDGE_UPDATE, True),
    (S_KNOWLEDGE_UPDATE, S_COMPLETED, True),
    (S_OBJECTIVE_CREATED, S_COMPLETED, False),
    (S_PLANNING, S_EXPERIMENT_RUNNING, False),
    (S_RESULT_ANALYSIS, S_PLANNING, False),
    (S_COMPLETED, S_PLANNING, False),
    (S_KNOWLEDGE_UPDATE, S_REVIEW_PENDING, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


def test_is_skip_pure():
    assert M.is_skip(S_OBJECTIVE_CREATED, S_EXPERIMENT_RUNNING) is True
    assert M.is_skip(S_OBJECTIVE_CREATED, S_PLANNING) is False


def test_is_reverse_pure():
    assert M.is_reverse(S_RESULT_ANALYSIS, S_PLANNING) is True
    assert M.is_reverse(S_PLANNING, S_RESULT_ANALYSIS) is False


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                  "DEPLOY_STRATEGY", "PROMOTE_MODEL", "APPROVE_LIVE",
                                  "MODIFY_PERMISSION", "CHANGE_CONFIG", "execute", "deploy"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["ORCHESTRATE", "ADVANCE", "COLLECT", "ROUTE", "INITIALIZE", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.pipeline_id("x") == M.pipeline_id("x")
    assert M.cycle_id("o", 1) == M.cycle_id("o", 1)
    assert M.objective_id("p", "t") == M.objective_id("p", "t")


def test_ids_prefixes_ap_scheme():
    assert M.pipeline_id("x").startswith("APG:")
    assert M.objective_id("p", "t").startswith("APO:")
    assert M.cycle_id("o", 1).startswith("APC:")
    assert M.run_id("c", "l").startswith("APR:")
    assert M.stage_id("c", "s").startswith("APS:")
    assert M.transition_event_id("c", "s", 0).startswith("APV:")
    assert M.history_id("c", "k", "r", 0).startswith("APH:")
    assert M.report_id("s", "i", "t").startswith("APN:")
    assert M.artifact_id("t", "r").startswith("APF:")


def test_transition_id_varies_with_seq():
    assert M.transition_event_id("c", "PLANNING", 0) != M.transition_event_id("c", "PLANNING", 1)


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p", "record_hash": "r"}
    b = {"x": 1, "previous_hash": "q", "record_hash": "s"}
    assert M.content_hash(a) == M.content_hash(b)


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []
    assert M.detect_cycle([("a", "b")]) == []


# ══════════════ 보안: 금지 import AST 스캔 ══════════════
_PKG_DIR = os.path.dirname(os.path.dirname(__file__))
_FORBIDDEN_PREFIXES = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.capital_allocation", "jarvis.live_trading", "jarvis.risk_controller",
    "jarvis.portfolio_execution",
)


def _module_files():
    for fn in os.listdir(_PKG_DIR):
        if fn.endswith(".py"):
            yield os.path.join(_PKG_DIR, fn)


def test_no_forbidden_imports():
    for path in _module_files():
        with open(path) as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                for bad in _FORBIDDEN_PREFIXES:
                    assert not name.startswith(bad), f"{path}: {name}"


def test_no_forbidden_method_defs():
    forbidden = ("def execute_trade", "def place_order", "def allocate_capital",
                 "def deploy_strategy", "def promote_model", "def approve_live",
                 "def modify_permission", "def change_config", "def execute", "def deploy")
    for path in _module_files():
        with open(path) as f:
            src = f.read().lower()
        for bad in forbidden:
            assert bad not in src, f"{path}: {bad}"


def test_no_model_id_leak():
    for path in _module_files():
        with open(path) as f:
            assert "claude-opus" not in f.read().lower()


def test_ledger_no_delete_update_api():
    import jarvis.autonomous_research_pipeline.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_arp_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.create_pipeline_run(cyc, "r", "", T[3], commit=True)
    e.attach_research_task(cyc, "experiment", "EXP1", "", T[4], commit=True)
    _advance_to(e, cyc, S_PLANNING, start_t=5)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("arp_"), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("agent_governance", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("arg_agents.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"event_id": "AG1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("agent_governance", "AG1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    assert main(["summary"]) == 0
    assert "cycle_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    main(["pipeline", "--name", "p", "--commit"])
    pl = json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"]
    main(["objective", "--pipeline", pl, "--title", "t", "--commit"])
    obj = json.loads(capsys.readouterr().out)["objective"]["objective_id"]
    main(["cycle", "--objective", obj, "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    assert main(["advance", "--cycle", cyc, "--to", "PLANNING", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["transition"]["to_stage"] == "PLANNING"


def test_cli_advance_and_state(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    main(["pipeline", "--name", "p", "--commit"])
    pl = json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"]
    main(["objective", "--pipeline", pl, "--title", "t", "--commit"])
    obj = json.loads(capsys.readouterr().out)["objective"]["objective_id"]
    main(["cycle", "--objective", obj, "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    main(["attach", "--cycle", cyc, "--ref-type", "experiment", "--ref-id", "EXP1", "--commit"])
    capsys.readouterr()
    assert main(["state", "--cycle", cyc]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "EXP1" in out["experiment"]


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    main(["pipeline", "--name", "p", "--commit"])
    pl = json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"]
    assert main(["report", "--scope-id", pl, "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["is_binding"] is False


# ══════════════ no stray writes ══════════════
def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_pipeline("p", "m", T[0], commit=False)
    assert ledger.read_pipelines() == []


@pytest.mark.parametrize("stage", list(_STAGE_SEQ))
def test_each_stage_reachable(tmp_path, monkeypatch, stage):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, stage)
    assert e.current_stage(cyc) == stage


@pytest.mark.parametrize("stage", list(CYCLE_STAGES))
def test_stage_order_indices(stage):
    assert stage in M.STAGE_ORDER
    assert 0 <= M.STAGE_ORDER[stage] <= 8


def test_stage_order_is_linear():
    idxs = [M.STAGE_ORDER[s] for s in CYCLE_STAGES]
    assert idxs == list(range(9))


def test_pipeline_run_creates_run_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    r = e.create_pipeline_run(cyc, "r1", "", T[3], commit=True)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_RUN]
    assert any(a["ref_id"] == r.run_id for a in arts)


def test_multiple_runs_per_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.create_pipeline_run(cyc, "r1", "", T[3], commit=True)
    e.create_pipeline_run(cyc, "r2", "", T[4], commit=True)
    assert len(ledger.cycle_runs(cyc)) == 2


def test_list_cycles_by_pipeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pl = _pipeline(e)
    obj = e.create_research_objective(pl, "t", "d", "", "", T[1], commit=True).objective_id
    e.initialize_cycle(obj, 1, T[2], commit=True)
    assert len(e.list_cycles(pl)) == 1


def test_stage_history_progression(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _advance_to(e, cyc, S_EXPERIMENT_DESIGN)
    hist = e.stage_history(cyc)
    assert hist == [S_OBJECTIVE_CREATED, S_PLANNING, S_HYPOTHESIS_FORMING, S_EXPERIMENT_DESIGN]


def test_state_model_unknown_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownCycleError):
        e.cycle_state_model("APC:ghost")


def test_attach_dedup_same_ref(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.attach_research_task(cyc, "agent", "AG1", "", T[3], commit=True)
    e.attach_research_task(cyc, "agent", "AG1", "", T[4], commit=True)
    # 두 이력 레코드지만 상태 모델은 dedup
    assert e.cycle_state_model(cyc)["agent"] == ["AG1"]
    assert len(ledger.cycle_history(cyc)) == 2


def test_report_cycle_scope(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    rep = e.generate_pipeline_report(cyc, "CYCLE", T[10], commit=True)
    assert rep.cycle_count == 1


def test_report_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pl = _pipeline(e)
    rep = e.generate_pipeline_report(pl, "PIPELINE", T[1], commit=True)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_REPORT]
    assert any(a["ref_id"] == rep.report_id for a in arts)


def test_transitions_are_marked_valid(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.advance_stage(cyc, S_PLANNING, "", T[3], commit=True)
    for tr in ledger.cycle_transitions(cyc):
        assert tr["valid"] is True


def test_cli_results_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    main(["pipeline", "--name", "p", "--commit"])
    pl = json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"]
    main(["objective", "--pipeline", pl, "--title", "t", "--commit"])
    obj = json.loads(capsys.readouterr().out)["objective"]["objective_id"]
    main(["cycle", "--objective", obj, "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    for st in ["PLANNING", "HYPOTHESIS_FORMING", "EXPERIMENT_DESIGN", "EXPERIMENT_RUNNING"]:
        main(["advance", "--cycle", cyc, "--to", st, "--commit"])
        capsys.readouterr()
    assert main(["results", "--cycle", cyc, "--result-ref", "RES1", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["history"]["ref_id"] == "RES1"


def test_cli_complete_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    main(["pipeline", "--name", "p", "--commit"])
    pl = json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"]
    main(["objective", "--pipeline", pl, "--title", "t", "--commit"])
    obj = json.loads(capsys.readouterr().out)["objective"]["objective_id"]
    main(["cycle", "--objective", obj, "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    for st in ["PLANNING", "HYPOTHESIS_FORMING", "EXPERIMENT_DESIGN", "EXPERIMENT_RUNNING",
               "RESULT_ANALYSIS", "REVIEW_PENDING", "KNOWLEDGE_UPDATE"]:
        main(["advance", "--cycle", cyc, "--to", st, "--commit"])
        capsys.readouterr()
    assert main(["complete", "--cycle", cyc, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["transition"]["to_stage"] == S_COMPLETED


def test_cli_review_routing(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    main(["pipeline", "--name", "p", "--commit"])
    pl = json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"]
    main(["objective", "--pipeline", pl, "--title", "t", "--commit"])
    obj = json.loads(capsys.readouterr().out)["objective"]["objective_id"]
    main(["cycle", "--objective", obj, "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    for st in ["PLANNING", "HYPOTHESIS_FORMING", "EXPERIMENT_DESIGN", "EXPERIMENT_RUNNING",
               "RESULT_ANALYSIS"]:
        main(["advance", "--cycle", cyc, "--to", st, "--commit"])
        capsys.readouterr()
    assert main(["review", "--cycle", cyc, "--review-ref", "REV1", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["transition"]["to_stage"] == S_REVIEW_PENDING


def test_cli_run_and_cycles(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_pipeline.__main__ import main
    main(["pipeline", "--name", "p", "--commit"])
    pl = json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"]
    main(["objective", "--pipeline", pl, "--title", "t", "--commit"])
    obj = json.loads(capsys.readouterr().out)["objective"]["objective_id"]
    main(["cycle", "--objective", obj, "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    assert main(["run", "--cycle", cyc, "--label", "r1", "--commit"]) == 0
    capsys.readouterr()
    assert main(["cycles", "--pipeline", pl]) == 0
    assert len(json.loads(capsys.readouterr().out)["cycles"]) == 1


def test_history_immutable_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.attach_research_task(cyc, "experiment", "EXP1", "d1", T[3], commit=True)
    # 다른 detail 로 다시 부착 → 새 이력 레코드(seq 다름), 기존 불변
    e.attach_research_task(cyc, "experiment", "EXP1", "d2", T[4], commit=True)
    hs = ledger.cycle_history(cyc)
    ids = [h["history_id"] for h in hs]
    assert len(ids) == len(set(ids))


def test_end_to_end_autonomous_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pl = _pipeline(e)
    obj = e.create_research_objective(pl, "momentum robustness", "d", "sharpe", "", T[1],
                                      commit=True).objective_id
    cyc = e.initialize_cycle(obj, 1, T[2], commit=True).cycle_id
    e.create_pipeline_run(cyc, "run1", "", T[3], commit=True)
    e.advance_stage(cyc, S_PLANNING, "", T[4], commit=True)
    e.advance_stage(cyc, S_HYPOTHESIS_FORMING, "", T[5], commit=True)
    e.attach_research_task(cyc, "hypothesis", "H1", "", T[6], commit=True)
    e.advance_stage(cyc, S_EXPERIMENT_DESIGN, "", T[7], commit=True)
    e.attach_research_task(cyc, "experiment", "EXP1", "", T[8], commit=True)
    e.attach_research_task(cyc, "agent", "AG1", "", T[9], commit=True)
    e.advance_stage(cyc, S_EXPERIMENT_RUNNING, "", T[10], commit=True)
    e.collect_results(cyc, "RES1", "sharpe 1.5", T[11], commit=True)
    e.advance_stage(cyc, S_RESULT_ANALYSIS, "", T[12], commit=True)
    e.trigger_review_stage(cyc, "REV1", T[13], commit=True)
    e.advance_stage(cyc, S_KNOWLEDGE_UPDATE, "", T[14], commit=True)
    e.attach_research_task(cyc, "memory", "MEM1", "", T[15], commit=True)
    e.complete_cycle(cyc, T[16], commit=True)
    assert e.current_stage(cyc) == S_COMPLETED
    model = e.cycle_state_model(cyc)
    assert model["hypothesis"] == ["H1"] and model["experiment"] == ["EXP1"]
    assert model["result"] == ["RES1"] and model["review"] == ["REV1"]
    assert verify_chain()["ok"] is True
