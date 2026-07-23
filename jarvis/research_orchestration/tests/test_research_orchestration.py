"""P10.17 Research Orchestration & Workflow Intelligence 테스트. **연구 과정 가시성·조정 전용.**

워크플로(불변·생명주기 CREATED→PLANNED→RUNNING→PAUSED→COMPLETED→ARCHIVED, 차단전이)·파이프라인(버전 불변·
중복)·태스크(생명주기 CREATED→READY→BLOCKED→IN_PROGRESS→COMPLETED→ARCHIVED)·의존 그래프(생성·순환·미등록)·
실행 이력·이벤트 이력·병목(플래그·해소 추적)·리포트(결정적)·verify(체인/변조/중복/의존/전이/계보)·replay·
상위 READ ONLY 보호·CLI·보안(금지import·실행/거래/배포/배분/트리거 없음·상위 원장 무변경·삭제 API 없음·불변·
WORKFLOW STATE≠EXECUTION STATE·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_orchestration import ledger
from jarvis.research_orchestration import models as M
from jarvis.research_orchestration.engine import ResearchOrchestrationEngine
from jarvis.research_orchestration.models import (
    ACKNOWLEDGED,
    ARCHIVED,
    BLOCKED,
    COMPLETED,
    CREATED,
    IN_PROGRESS,
    OPEN,
    PAUSED,
    PLANNED,
    READY,
    RESOLVED,
    RUNNING,
    IllegalTransition,
    ImmutablePipelineError,
    ImmutableWorkflowError,
    InvalidBottleneckCategory,
    InvalidDependencyGraph,
    UnknownBottleneck,
    UnknownTask,
    UnknownWorkflow,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"task_completion_rate": 0.9, "dependency_health": 0.85, "bottleneck_resolution_rate": 0.8,
       "workflow_progress": 0.9, "lineage_completeness": 0.8}
_LO = {"task_completion_rate": 0.1, "dependency_health": 0.2, "bottleneck_resolution_rate": 0.1,
       "workflow_progress": 0.2, "lineage_completeness": 0.1}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_orchestration.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchOrchestrationEngine()


def _wf(eng, name="alpha_research", version="1.0", objective="find edge", meta=None, commit=True):
    return eng.create_workflow(name, version, objective, meta or {}, T0, commit=commit)


def _task(eng, wid, name="backtest", ttype=M.T_BACKTEST, deps=None, commit=True):
    return eng.register_task(wid, name, ttype, deps or [], T0, commit=commit)


def _bottleneck(eng, src="ORT:x", cat=None, sev="HIGH", commit=True):
    return eng.detect_bottleneck(src, cat or M.B_DEPENDENCY_BLOCK, sev, ["ev1"], T0, commit=commit)


def _full(eng):
    """workflow→pipeline→tasks→dependency→run→event→bottleneck→report end-to-end."""
    w = _wf(eng)
    eng.create_pipeline(w.workflow_id, ["prep", "backtest", "validate"], "1.0", {}, T0, commit=True)
    t1 = _task(eng, w.workflow_id, name="prep", ttype=M.T_DATA_PREP)
    t2 = _task(eng, w.workflow_id, name="backtest", ttype=M.T_BACKTEST)
    eng.add_dependency(t2.task_id, t1.task_id, "REQUIRES", T0, commit=True)
    eng.update_workflow_state(w.workflow_id, PLANNED, T1, commit=True)
    eng.record_run(w.workflow_id, "MANUAL", "RECORDED", "n", T1, commit=True)
    eng.detect_bottleneck(t2.task_id, M.B_DATA_MISSING, "MEDIUM", ["e"], T1, commit=True)
    eng.generate_report("GLOBAL", _HI, T2, commit=True)
    return w, t1, t2


# ── Workflow ──
def test_workflow_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    w = _wf(_eng())
    assert w.workflow_id.startswith("ORW:")
    assert w.to_state == CREATED
    assert w.objective == "find edge"


def test_workflow_persisted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _wf(_eng())
    assert len(ledger.distinct_workflows()) == 1


def test_workflow_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _wf(_eng(), commit=False)
    assert ledger.read_workflow_events() == []


def test_workflow_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    w = _wf(_eng())
    assert w.workflow_id == M.workflow_id("alpha_research")


def test_workflow_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _wf(eng)
    b = _wf(eng)
    assert a.workflow_id == b.workflow_id
    assert len(ledger.distinct_workflows()) == 1


def test_workflow_immutable_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _wf(eng, objective="A")
    with pytest.raises(ImmutableWorkflowError):
        _wf(eng, objective="B")


def test_workflow_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    assert eng.workflow_state(w.workflow_id) == CREATED


def test_workflow_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    for st in (PLANNED, RUNNING, PAUSED, RUNNING, COMPLETED, ARCHIVED):
        eng.update_workflow_state(w.workflow_id, st, T1, commit=True)
    assert eng.workflow_state(w.workflow_id) == ARCHIVED


def test_workflow_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    with pytest.raises(IllegalTransition):
        eng.update_workflow_state(w.workflow_id, RUNNING, T1, commit=True)


def test_workflow_pause_from_created_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    with pytest.raises(IllegalTransition):
        eng.update_workflow_state(w.workflow_id, PAUSED, T1, commit=True)


def test_workflow_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownWorkflow):
        _eng().update_workflow_state("ORW:nope", PLANNED, T1, commit=True)


def test_workflow_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    eng.update_workflow_state(w.workflow_id, ARCHIVED, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.update_workflow_state(w.workflow_id, PLANNED, T1, commit=True)


def test_workflow_can_transition_table():
    assert M.can_transition_workflow("", CREATED)
    assert M.can_transition_workflow(RUNNING, PAUSED)
    assert M.can_transition_workflow(PAUSED, RUNNING)
    assert not M.can_transition_workflow(CREATED, RUNNING)
    assert not M.can_transition_workflow(COMPLETED, RUNNING)


def test_workflow_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    w = _wf(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_WORKFLOW, w.workflow_id))


def test_workflow_state_change_records_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    eng.update_workflow_state(w.workflow_id, PLANNED, T1, commit=True)
    evs = [e for e in ledger.read_events() if e["event_type"] == M.EV_STATE_CHANGED]
    assert len(evs) == 1


# ── Pipeline ──
def test_pipeline_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    p = eng.create_pipeline(w.workflow_id, ["s1", "s2"], "1.0", {}, T0, commit=True)
    assert p.pipeline_id.startswith("ORP:")
    assert p.stages == ["s1", "s2"]


def test_pipeline_requires_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownWorkflow):
        _eng().create_pipeline("ORW:nope", ["s1"], "1.0", {}, T0, commit=True)


def test_pipeline_version_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    eng.create_pipeline(w.workflow_id, ["s1"], "1.0", {}, T0, commit=True)
    with pytest.raises(ImmutablePipelineError):
        eng.create_pipeline(w.workflow_id, ["s1", "s2"], "1.0", {}, T0, commit=True)


def test_pipeline_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    a = eng.create_pipeline(w.workflow_id, ["s1"], "1.0", {}, T0, commit=True)
    b = eng.create_pipeline(w.workflow_id, ["s1"], "1.0", {}, T0, commit=True)
    assert a.pipeline_id == b.pipeline_id
    assert len(ledger.read_pipelines()) == 1


def test_pipeline_multiple_versions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    p1 = eng.create_pipeline(w.workflow_id, ["s1"], "1.0", {}, T0, commit=True)
    p2 = eng.create_pipeline(w.workflow_id, ["s1", "s2"], "2.0", {}, T0, commit=True)
    assert p1.pipeline_id != p2.pipeline_id
    assert len(ledger.pipelines_for(w.workflow_id)) == 2


def test_pipeline_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    p = eng.create_pipeline(w.workflow_id, ["s1"], "1.0", {}, T0, commit=True)
    assert p.pipeline_id == M.pipeline_id(w.workflow_id, "1.0")


def test_pipeline_parent_links_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    p = eng.create_pipeline(w.workflow_id, ["s1"], "1.0", {}, T0, commit=True)
    pa = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == p.pipeline_id and a["artifact_type"] == M.ART_PIPELINE)
    assert pa["parent_artifact"] == M.artifact_id(M.ART_WORKFLOW, w.workflow_id)


# ── Task ──
def test_task_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    assert t.task_id.startswith("ORT:")
    assert t.to_state == CREATED
    assert t.task_type == M.T_BACKTEST


def test_task_requires_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownWorkflow):
        _eng().register_task("ORW:nope", "t1", "ANALYSIS", [], T0, commit=True)


def test_task_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    for st in (READY, IN_PROGRESS, COMPLETED, ARCHIVED):
        eng.update_task_state(t.task_id, st, T1, commit=True)
    assert eng.task_state(t.task_id) == ARCHIVED


def test_task_blocking(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    eng.update_task_state(t.task_id, READY, T1, commit=True)
    eng.update_task_state(t.task_id, BLOCKED, T1, commit=True)
    assert eng.task_state(t.task_id) == BLOCKED
    eng.update_task_state(t.task_id, READY, T2, commit=True)
    assert eng.task_state(t.task_id) == READY


def test_task_completion(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    eng.update_task_state(t.task_id, READY, T1, commit=True)
    eng.update_task_state(t.task_id, IN_PROGRESS, T1, commit=True)
    eng.update_task_state(t.task_id, COMPLETED, T2, commit=True)
    assert eng.task_state(t.task_id) == COMPLETED


def test_task_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    with pytest.raises(IllegalTransition):
        eng.update_task_state(t.task_id, COMPLETED, T1, commit=True)


def test_task_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownTask):
        _eng().update_task_state("ORT:nope", READY, T1, commit=True)


def test_task_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    a = _task(eng, w.workflow_id)
    b = _task(eng, w.workflow_id)
    assert a.task_id == b.task_id
    assert len(ledger.distinct_tasks()) == 1


def test_task_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id, name="prep")
    assert t.task_id == M.task_id(w.workflow_id, "prep")


def test_task_all_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    for i, tt in enumerate(M.TASK_TYPES):
        t = _task(eng, w.workflow_id, name=f"t{i}", ttype=tt)
        assert t.task_type == tt
    assert len(ledger.distinct_tasks()) == len(M.TASK_TYPES)


def test_task_parent_links_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    ta = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == t.task_id and a["artifact_type"] == M.ART_TASK)
    assert ta["parent_artifact"] == M.artifact_id(M.ART_WORKFLOW, w.workflow_id)


def test_task_can_transition_table():
    assert M.can_transition_task("", CREATED)
    assert M.can_transition_task(IN_PROGRESS, COMPLETED)
    assert M.can_transition_task(BLOCKED, READY)
    assert not M.can_transition_task(CREATED, COMPLETED)


# ── Dependency Graph ──
def test_dependency_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t1 = _task(eng, w.workflow_id, name="a")
    t2 = _task(eng, w.workflow_id, name="b")
    d = eng.add_dependency(t2.task_id, t1.task_id, "REQUIRES", T0, commit=True)
    assert d.dependency_id.startswith("ORD:")
    assert d.from_task == t2.task_id
    assert d.to_task == t1.task_id


def test_dependency_missing_from(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t1 = _task(eng, w.workflow_id, name="a")
    with pytest.raises(InvalidDependencyGraph):
        eng.add_dependency("ORT:ghost", t1.task_id, "REQUIRES", T0, commit=True)


def test_dependency_missing_to(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t1 = _task(eng, w.workflow_id, name="a")
    with pytest.raises(InvalidDependencyGraph):
        eng.add_dependency(t1.task_id, "ORT:ghost", "REQUIRES", T0, commit=True)


def test_dependency_self_reference(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t1 = _task(eng, w.workflow_id, name="a")
    with pytest.raises(InvalidDependencyGraph):
        eng.add_dependency(t1.task_id, t1.task_id, "REQUIRES", T0, commit=True)


def test_dependency_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    a = _task(eng, w.workflow_id, name="a")
    b = _task(eng, w.workflow_id, name="b")
    eng.add_dependency(a.task_id, b.task_id, "REQUIRES", T0, commit=True)
    with pytest.raises(InvalidDependencyGraph):
        eng.add_dependency(b.task_id, a.task_id, "REQUIRES", T0, commit=True)


def test_dependency_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    a = _task(eng, w.workflow_id, name="a")
    b = _task(eng, w.workflow_id, name="b")
    c = _task(eng, w.workflow_id, name="c")
    eng.add_dependency(b.task_id, a.task_id, "REQUIRES", T0, commit=True)
    eng.add_dependency(c.task_id, b.task_id, "REQUIRES", T0, commit=True)
    assert eng.dependency_cycle() == []
    assert len(ledger.read_dependencies()) == 2


def test_dependency_task_dependencies(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    a = _task(eng, w.workflow_id, name="a")
    b = _task(eng, w.workflow_id, name="b")
    eng.add_dependency(a.task_id, b.task_id, "REQUIRES", T0, commit=True)
    assert eng.task_dependencies(a.task_id) == [b.task_id]


def test_dependency_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    a = _task(eng, w.workflow_id, name="a")
    b = _task(eng, w.workflow_id, name="b")
    d = eng.add_dependency(a.task_id, b.task_id, "REQUIRES", T0, commit=True)
    assert d.dependency_id == M.dependency_id(a.task_id, b.task_id)


def test_dependency_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    a = _task(eng, w.workflow_id, name="a")
    b = _task(eng, w.workflow_id, name="b")
    eng.add_dependency(a.task_id, b.task_id, "REQUIRES", T0, commit=True)
    eng.add_dependency(a.task_id, b.task_id, "REQUIRES", T0, commit=True)
    assert len(ledger.read_dependencies()) == 1


# ── Run History ──
def test_run_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    r = eng.record_run(w.workflow_id, "MANUAL", "RECORDED", "note", T0, commit=True)
    assert r.run_id.startswith("ORR:")
    assert r.sequence == 1


def test_run_sequences(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    eng.record_run(w.workflow_id, "MANUAL", "RECORDED", "", T0, commit=True)
    r2 = eng.record_run(w.workflow_id, "MANUAL", "RECORDED", "", T1, commit=True)
    assert r2.sequence == 2
    assert len(ledger.runs_for(w.workflow_id)) == 2


def test_run_requires_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownWorkflow):
        _eng().record_run("ORW:nope", "MANUAL", "RECORDED", "", T0, commit=True)


# ── Event History ──
def test_event_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng().record_event("ORW:x", M.EV_TASK_REGISTERED, "ref1", T0, commit=True)
    assert e.event_id.startswith("OEV:")
    assert len(ledger.read_events()) == 1


def test_event_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng().record_event("scope", "TYPE", "ref", T0, commit=True)
    assert e.event_id == M.event_id("scope", "TYPE", "ref")


# ── Bottleneck ──
def test_bottleneck_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    b = _bottleneck(_eng())
    assert b.bottleneck_id.startswith("ORB:")
    assert b.to_state == OPEN
    assert b.category == M.B_DEPENDENCY_BLOCK


def test_bottleneck_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidBottleneckCategory):
        _eng().detect_bottleneck("ORT:x", "not_a_cat", "LOW", [], T0, commit=True)


def test_bottleneck_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, cat in enumerate(M.BOTTLENECK_CATEGORIES):
        b = eng.detect_bottleneck(f"ORT:{i}", cat, "MEDIUM", [], T0, commit=True)
        assert b.category == cat
    assert len(ledger.distinct_bottlenecks()) == len(M.BOTTLENECK_CATEGORIES)


def test_bottleneck_resolution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = _bottleneck(eng)
    eng.resolve_bottleneck(b.bottleneck_id, T1, commit=True)
    assert eng.bottleneck_state(b.bottleneck_id) == RESOLVED


def test_bottleneck_acknowledge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = _bottleneck(eng)
    eng.transition_bottleneck(b.bottleneck_id, ACKNOWLEDGED, T1, commit=True)
    assert eng.bottleneck_state(b.bottleneck_id) == ACKNOWLEDGED


def test_bottleneck_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = _bottleneck(eng)
    eng.transition_bottleneck(b.bottleneck_id, RESOLVED, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_bottleneck(b.bottleneck_id, OPEN, T2, commit=True)


def test_bottleneck_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownBottleneck):
        _eng().transition_bottleneck("ORB:nope", RESOLVED, T1, commit=True)


def test_bottleneck_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _bottleneck(eng)
    b = _bottleneck(eng)
    assert a.bottleneck_id == b.bottleneck_id
    assert len(ledger.distinct_bottlenecks()) == 1


def test_bottleneck_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    b = _bottleneck(_eng())
    assert b.bottleneck_id == M.bottleneck_id("ORT:x", M.B_DEPENDENCY_BLOCK)


def test_bottleneck_parent_links_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    b = eng.detect_bottleneck(t.task_id, M.B_VALIDATION_FAILED, "HIGH", [], T0, commit=True)
    ba = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == b.bottleneck_id and a["artifact_type"] == M.ART_BOTTLENECK)
    assert ba["parent_artifact"] == M.artifact_id(M.ART_TASK, t.task_id)


def test_bottleneck_can_transition_table():
    assert M.can_transition_bottleneck("", OPEN)
    assert M.can_transition_bottleneck(OPEN, ACKNOWLEDGED)
    assert M.can_transition_bottleneck(ACKNOWLEDGED, RESOLVED)
    assert not M.can_transition_bottleneck(RESOLVED, OPEN)


def test_bottleneck_severity_weight():
    assert M.severity_weight("CRITICAL") == 1.0
    assert M.severity_weight("LOW") == 0.25


# ── Orchestration score / analyze ──
def test_orch_score_high():
    assert M.orchestration_score(_HI) > 0.7


def test_orch_score_low():
    assert M.orchestration_score(_LO) < 0.4


def test_orch_score_empty_zero():
    assert M.orchestration_score({}) == 0.0


def test_orch_weights_sum_one():
    assert abs(sum(M.ORCH_WEIGHTS.values()) - 1.0) < 1e-9


def test_orch_health_labels():
    assert M.orchestration_health(_HI) == "HEALTHY"
    assert M.orchestration_health(_LO) == "DEGRADED"
    assert M.orchestration_health({"task_completion_rate": 1.0, "dependency_health": 1.0}) == \
        "WARNING"


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HI)
    assert res["orchestration_health"] == "HEALTHY"
    assert res["orchestration_score"] > 0.7


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.report_id.startswith("ORX:")
    assert r.workflow_count >= 1
    assert r.task_count >= 2
    assert r.dependency_count >= 1


def test_report_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert PLANNED in r.workflow_state_distribution
    assert CREATED in r.task_state_distribution


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    a = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    b = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert "ORCHESTRATION ≠ AUTOMATION" in r.disclaimer


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


def test_report_health_label(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert r.orchestration_health == "HEALTHY"


# ── Lineage / verify ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    anc = eng.trace_lineage(M.artifact_id(M.ART_TASK, t.task_id))
    assert M.artifact_id(M.ART_WORKFLOW, w.workflow_id) in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_orchestration.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _wf(eng)
    p = sp("or_workflows.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["objective"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_orchestration.verify import verify_ledger
    assert verify_ledger(ledger.WORKFLOWS)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    eng.record_run(w.workflow_id, "MANUAL", "RECORDED", "", T0, commit=True)
    eng.record_run(w.workflow_id, "MANUAL", "RECORDED", "", T1, commit=True)
    p = sp("or_runs.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_orchestration.verify import verify_ledger
    assert verify_ledger(ledger.RUNS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _wf(eng)
    p = sp("or_workflows.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))  # duplicate id
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_orchestration.verify import verify_ledger
    assert verify_ledger(ledger.WORKFLOWS)["ok"] is False


def test_verify_dependency_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_orchestration.verify import dependency_validation
    assert dependency_validation()["ok"] is True


def test_verify_dependency_dangling(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    a = _task(eng, w.workflow_id, name="a")
    b = _task(eng, w.workflow_id, name="b")
    eng.add_dependency(a.task_id, b.task_id, "REQUIRES", T0, commit=True)
    # inject a dependency referencing a ghost task, bypassing engine guards
    from jarvis.research_orchestration.models import content_hash, dependency_id
    did = dependency_id(a.task_id, "ORT:ghost")
    rec = {"dependency_id": did, "from_task": a.task_id, "to_task": "ORT:ghost",
           "relation": "REQUIRES", "created_at": T0, "input_hash": "", "record_hash": "",
           "previous_hash": ledger.dependencies_head()["record_hash"]}
    rec["record_hash"] = content_hash(rec)
    ledger.append_dependency(rec)
    from jarvis.research_orchestration.verify import dependency_validation
    res = dependency_validation()
    assert res["ok"] is False
    assert any("dangling" in i for i in res["issues"])


def test_verify_workflow_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    eng.update_workflow_state(w.workflow_id, PLANNED, T1, commit=True)
    from jarvis.research_orchestration.verify import workflow_transition_validation
    assert workflow_transition_validation()["ok"] is True


def test_verify_task_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    eng.update_task_state(t.task_id, READY, T1, commit=True)
    from jarvis.research_orchestration.verify import task_transition_validation
    assert task_transition_validation()["ok"] is True


def test_verify_detects_bad_workflow_transition(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _wf(eng)
    p = sp("or_workflows.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["to_state"] = "RUNNING"  # illegal from GENESIS
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_orchestration.verify import workflow_transition_validation
    assert workflow_transition_validation()["ok"] is False


def test_verify_bottleneck_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = _bottleneck(eng)
    eng.resolve_bottleneck(b.bottleneck_id, T1, commit=True)
    from jarvis.research_orchestration.verify import bottleneck_transition_validation
    assert bottleneck_transition_validation()["ok"] is True


# ── replay / summary ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_orchestration.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert s.workflow_count >= 1
    assert s.pipeline_count >= 1
    assert s.task_count >= 2
    assert s.dependency_count >= 1
    assert s.run_count >= 1
    assert s.bottleneck_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


def test_full_verify_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.research_orchestration.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["workflow_transitions"]["ok"] is True
    assert res["task_transitions"]["ok"] is True
    assert res["bottleneck_transitions"]["ok"] is True
    assert res["dependency"]["ok"] is True
    assert res["lineage"]["ok"] is True


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


# ── CLI ──
def test_cli_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.__main__ import main
    rc = main(["workflow", "--name", "wf1", "--objective", "edge", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["workflow"]["workflow_id"].startswith("ORW:")


def test_cli_pipeline(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.__main__ import main
    main(["workflow", "--name", "wf1", "--commit"])
    wid = json.loads(capsys.readouterr().out)["workflow"]["workflow_id"]
    rc = main(["pipeline", "--workflow-id", wid, "--stages", "a,b", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"].startswith("ORP:")


def test_cli_task_and_dependency(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.__main__ import main
    main(["workflow", "--name", "wf1", "--commit"])
    wid = json.loads(capsys.readouterr().out)["workflow"]["workflow_id"]
    main(["task", "--workflow-id", wid, "--name", "a", "--commit"])
    ta = json.loads(capsys.readouterr().out)["task"]["task_id"]
    main(["task", "--workflow-id", wid, "--name", "b", "--commit"])
    tb = json.loads(capsys.readouterr().out)["task"]["task_id"]
    rc = main(["dependency", "--from-task", ta, "--to-task", tb, "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dependency"]["dependency_id"].startswith("ORD:")
    assert out["cycle"] == []


def test_cli_event(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.__main__ import main
    rc = main(["event", "--scope", "s", "--event-type", "STATE_CHANGED", "--reference", "r",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["event"]["event_id"].startswith("OEV:")


def test_cli_bottleneck(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.__main__ import main
    rc = main(["bottleneck", "--source-task", "ORT:x", "--category", "data_missing", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["bottleneck"]["bottleneck_id"].startswith("ORB:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.__main__ import main
    rc = main(["report", "--metrics-json", json.dumps(_HI), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("ORX:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.__main__ import main
    main(["workflow", "--name", "wf1", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.__main__ import main
    main(["workflow", "--name", "wf1", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_orchestration.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "workflow_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_orchestration.engine as eng_mod
    import jarvis.research_orchestration.models as mdl_mod
    import jarvis.research_orchestration.ledger as led_mod
    import jarvis.research_orchestration.verify as ver_mod
    import jarvis.research_orchestration.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "activate_live(", "modify_config(", "change_permission(",
                 "auto_start("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.research_orchestration.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def deploy", "def trade", "def place_order",
               "def allocate_capital", "def activate_live", "def modify_config",
               "def change_permission", "def auto_start"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchOrchestrationEngine))
    for banned in ("execute", "deploy", "trade", "place_order", "allocate_capital",
                   "activate_live", "modify_config", "change_permission", "auto_start"):
        assert banned not in api


def test_workflow_state_not_execution_state(tmp_path, monkeypatch):
    """워크플로 이벤트에 execute/deploy/order 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    w = _wf(_eng())
    d = w.to_dict()
    for banned in ("execute", "deploy", "order", "capital", "position"):
        assert banned not in d


def test_task_not_running_process(tmp_path, monkeypatch):
    """태스크 이벤트에 process/pid/execute 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id)
    d = t.to_dict()
    for banned in ("pid", "process", "execute", "order"):
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
        m = importlib.import_module(f"jarvis.research_orchestration.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("remove_")
            # update_task_state / update_workflow_state are lifecycle recorders (append-only)
            if low.startswith("update_"):
                assert "state" in low


def test_ledger_prefix_or(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("or_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 9


def test_engine_no_upstream_layer_import():
    import jarvis.research_orchestration.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.research_evolution", "import jarvis.meta_intelligence",
               "import jarvis.research_os", "import jarvis.self_improvement"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.workflow_id("a")[:4],
        M.workflow_event_id("a", "", CREATED)[:4],
        M.pipeline_id("a", "1")[:4],
        M.task_id("a", "b")[:4],
        M.task_event_id("a", "", CREATED)[:4],
        M.dependency_id("a", "b")[:4],
        M.run_id("a", 1)[:4],
        M.event_id("a", "b", "c")[:4],
        M.bottleneck_id("a", "b")[:4],
        M.bottleneck_event_id("a", "", OPEN)[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 12


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_metadata_hash_order_independent():
    assert M.metadata_hash({"a": 1, "b": 2}) == M.metadata_hash({"b": 2, "a": 1})


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_workflow_states_count():
    assert len(M.WORKFLOW_STATES) == 6


def test_task_states_count():
    assert len(M.TASK_STATES) == 6


def test_bottleneck_states_count():
    assert len(M.BOTTLENECK_STATES) == 4


def test_bottleneck_categories_count():
    assert len(M.BOTTLENECK_CATEGORIES) == 6


def test_task_types_count():
    assert len(M.TASK_TYPES) == 8


def test_node_types_count():
    assert len(M.NODE_TYPES) == 5


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _wf(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_workflow_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    w = _wf(_eng())
    d = w.to_dict()
    assert d["workflow_id"] == w.workflow_id
    assert set(("name", "version", "objective")).issubset(d)


def test_report_bottleneck_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = _bottleneck(eng)
    eng.resolve_bottleneck(b.bottleneck_id, T1, commit=True)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.bottleneck_state_distribution.get(RESOLVED) == 1


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


def test_workflow_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    w = _wf(_eng())
    assert w.input_hash == M.input_digest(w.workflow_id, "", CREATED)


def test_task_dependencies_field_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    t = _task(eng, w.workflow_id, deps=["ORT:dep1"])
    assert t.dependencies == ["ORT:dep1"]


def test_bottleneck_evidence_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    b = _bottleneck(_eng())
    assert b.evidence == ["ev1"]


def test_pipeline_stages_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    p = eng.create_pipeline(w.workflow_id, ["prep", "test"], "1.0", {}, T0, commit=True)
    assert p.stages == ["prep", "test"]


def test_run_status_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    r = eng.record_run(w.workflow_id, "SCHEDULED", "RECORDED", "note", T0, commit=True)
    assert r.trigger == "SCHEDULED"
    assert r.status == "RECORDED"


def test_summary_state_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert PLANNED in s.workflow_state_distribution
    assert CREATED in s.task_state_distribution


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _wf(eng)
    from jarvis.research_orchestration.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "ORA:c1", "artifact_type": "TASK", "ref_id": "x1",
          "parent_artifact": "ORA:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "ORA:c2", "artifact_type": "TASK", "ref_id": "x2",
          "parent_artifact": "ORA:c1", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": a1["record_hash"]}
    a2["record_hash"] = content_hash(a2)
    ledger.append_artifact(a2)
    res = eng.verify_lineage()
    assert res["ok"] is False
    assert any("cycle" in i for i in res["issues"])


def test_source_ledgers_not_or_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("or_")
        assert isinstance(idf, str)


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w1 = _wf(eng, name="wf1")
    w2 = _wf(eng, name="wf2")
    assert w1.workflow_id != w2.workflow_id
    assert len(ledger.distinct_workflows()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    for phrase in ("WORKFLOW STATE ≠ EXECUTION STATE", "TASK READY ≠ RUNNING PROCESS",
                   "WORKFLOW COMPLETED ≠ DEPLOYMENT", "ORCHESTRATION ≠ AUTOMATION"):
        assert phrase in r.disclaimer


def test_orch_score_partial_metrics():
    s = M.orchestration_score({"task_completion_rate": 1.0, "workflow_progress": 1.0})
    assert abs(s - (0.30 + 0.15)) < 1e-9


def test_workflow_pause_resume_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    eng.update_workflow_state(w.workflow_id, PLANNED, T1, commit=True)
    eng.update_workflow_state(w.workflow_id, RUNNING, T1, commit=True)
    eng.update_workflow_state(w.workflow_id, PAUSED, T1, commit=True)
    eng.update_workflow_state(w.workflow_id, RUNNING, T2, commit=True)
    eng.update_workflow_state(w.workflow_id, COMPLETED, T2, commit=True)
    assert eng.workflow_state(w.workflow_id) == COMPLETED
