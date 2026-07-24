"""P18 research_operations 테스트 — 워크플로/작업 생애주기·의존 DAG·순환·런·계획·이벤트·
계보·verify·replay·CLI·보안·금지능력."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_operations import ledger
from jarvis.research_operations import models as M
from jarvis.research_operations.engine import ResearchOperationsEngine
from jarvis.research_operations.models import (
    ALLOWED_TASK_TRANSITIONS,
    ALLOWED_WORKFLOW_TRANSITIONS,
    EVENT_TYPES,
    FORBIDDEN_VERBS,
    GENESIS,
    TASK_STATES,
    T_BLOCKED,
    T_CANCELLED,
    T_COMPLETED,
    T_CREATED,
    T_FAILED,
    T_QUEUED,
    T_RUNNING,
    WORKFLOW_STATES,
    W_ARCHIVED,
    W_COMPLETED,
    W_DEFINED,
    W_DRAFT,
    W_FAILED,
    W_PAUSED,
    W_READY,
    W_RUNNING,
    CircularDependencyError,
    DanglingDependencyError,
    IllegalTaskTransition,
    IllegalWorkflowTransition,
    ImmutableTaskError,
    ImmutableWorkflowError,
    UnknownTaskError,
    UnknownWorkflowError,
    can_task_transition,
    can_workflow_transition,
    content_hash,
    detect_cycle,
    is_forbidden_verb,
    topological_order,
)
from jarvis.research_operations.verify import (
    dependency_integrity,
    duplicate_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    task_lifecycle_integrity,
    verify_chain,
    workflow_lifecycle_integrity,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_operations.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchOperationsEngine()


def _wf(e, name="wf1", desc="d", now=T[0]):
    return e.create_workflow(name, desc, now, commit=True).workflow_id


def _task(e, wf, name="t1", desc="td", prio=0, meta=None, now=T[1]):
    return e.add_task(wf, name, desc, "owner", prio, meta or {}, now, commit=True).task_id


def _running_wf(e, name="wf1"):
    wf = _wf(e, name)
    t = _task(e, wf)
    e.ready_workflow(wf, T[2], commit=True)
    e.start_run(wf, "", "", T[3], commit=True)
    return wf, t


# ═══════════════ create_workflow ═══════════════
def test_create_workflow_draft(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_workflow("w", "d", T[0], commit=True)
    assert ev.to_state == W_DRAFT
    assert ev.from_state == GENESIS


def test_workflow_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_workflow("w", "d", T[0], commit=True)
    assert ev.workflow_id.startswith("WOK:")
    assert ev.workflow_event_id.startswith("WOW:")


def test_create_workflow_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e)
    assert len(ledger.read_workflow_events()) == 1


def test_create_workflow_records_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e)
    assert any(ev["event_type"] == "WORKFLOW_CREATED" for ev in ledger.read_events())


def test_create_workflow_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_workflow("w", "d", T[0], commit=True).workflow_id
    b = e.create_workflow("w", "d", T[1], commit=True).workflow_id
    assert a == b
    assert len(ledger.workflow_events(a)) == 1


def test_create_workflow_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_workflow("w", "d1", T[0], commit=True)
    with pytest.raises(ImmutableWorkflowError):
        e.create_workflow("w", "d2", T[1], commit=True)


def test_create_workflow_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_workflow("w", "d", T[0], commit=False)
    assert ledger.read_workflow_events() == []


def test_create_workflow_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e)
    assert any(a["artifact_type"] == "WORKFLOW" for a in ledger.read_artifacts())


# ═══════════════ workflow lifecycle ═══════════════
def test_add_task_transitions_defined(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf)
    assert e.workflow_state(wf) == W_DEFINED


def test_ready_requires_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    e.define_workflow(wf, T[1], commit=True)
    with pytest.raises(IllegalWorkflowTransition):
        e.ready_workflow(wf, T[2], commit=True)


def test_full_workflow_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    t = _task(e, wf)
    e.ready_workflow(wf, T[2], commit=True)
    e.start_run(wf, "", "", T[3], commit=True)
    assert e.workflow_state(wf) == W_RUNNING
    e.complete_workflow(wf, T[4], commit=True)
    e.archive_workflow(wf, T[5], commit=True)
    assert e.workflow_state(wf) == W_ARCHIVED


def test_workflow_no_skip_ready_from_draft(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    # DRAFT → READY 스킵 불가
    with pytest.raises(IllegalWorkflowTransition):
        e.ready_workflow(wf, T[2], commit=True)


def test_workflow_pause_resume(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf, t = _running_wf(e)
    e.pause_workflow(wf, T[4], commit=True)
    assert e.workflow_state(wf) == W_PAUSED
    e.resume_workflow(wf, T[5], commit=True)
    assert e.workflow_state(wf) == W_RUNNING


def test_workflow_fail_retry(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf, t = _running_wf(e)
    e.fail_workflow(wf, T[4], commit=True)
    assert e.workflow_state(wf) == W_FAILED
    e.ready_workflow(wf, T[5], commit=True)  # FAILED → READY 재시도
    assert e.workflow_state(wf) == W_READY


def test_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf, t = _running_wf(e)
    e.complete_workflow(wf, T[4], commit=True)
    e.archive_workflow(wf, T[5], commit=True)
    with pytest.raises(IllegalWorkflowTransition):
        e.resume_workflow(wf, T[6], commit=True)


def test_workflow_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownWorkflowError):
        _eng().define_workflow("WOK:nope", T[1], commit=True)


# ═══════════════ can_workflow_transition matrix ═══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (W_DRAFT, W_DEFINED, True), (W_DRAFT, W_READY, False), (W_DRAFT, W_RUNNING, False),
    (W_DEFINED, W_READY, True), (W_DEFINED, W_RUNNING, False),
    (W_READY, W_RUNNING, True), (W_READY, W_COMPLETED, False),
    (W_RUNNING, W_PAUSED, True), (W_RUNNING, W_COMPLETED, True), (W_RUNNING, W_FAILED, True),
    (W_PAUSED, W_RUNNING, True), (W_PAUSED, W_COMPLETED, False),
    (W_COMPLETED, W_ARCHIVED, True), (W_COMPLETED, W_RUNNING, False),
    (W_FAILED, W_READY, True), (W_FAILED, W_ARCHIVED, True),
    (W_ARCHIVED, W_DRAFT, False),
])
def test_workflow_transition_matrix(frm, to, ok):
    assert can_workflow_transition(frm, to) is ok


@pytest.mark.parametrize("s", WORKFLOW_STATES)
def test_workflow_states_in_map(s):
    assert s in ALLOWED_WORKFLOW_TRANSITIONS


def test_workflow_eight_states():
    assert len(WORKFLOW_STATES) == 8


def test_archived_no_transitions():
    assert ALLOWED_WORKFLOW_TRANSITIONS[W_ARCHIVED] == set()


# ═══════════════ tasks ═══════════════
def test_add_task_created(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    t = e.add_task(wf, "task", "d", "o", 3, {"resource": 2}, T[1], commit=True)
    assert t.task_id.startswith("WOT:")
    assert t.to_status == T_CREATED
    assert t.priority == 3


def test_add_task_unknown_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownWorkflowError):
        _eng().add_task("WOK:nope", "t", now=T[1], commit=True)


def test_add_task_after_running_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf, t = _running_wf(e)
    with pytest.raises(IllegalWorkflowTransition):
        e.add_task(wf, "late", now=T[5], commit=True)


def test_add_task_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    e.add_task(wf, "t", "d1", now=T[1], commit=True)
    with pytest.raises(ImmutableTaskError):
        e.add_task(wf, "t", "d2", now=T[2], commit=True)


def test_task_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    t = _task(e, wf)
    e.queue_task(t, T[2], commit=True)
    e.start_task(t, T[3], commit=True)
    e.complete_task(t, T[4], commit=True)
    assert e.task_status(t) == T_COMPLETED


def test_task_fail(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    t = _task(e, wf)
    e.queue_task(t, T[2], commit=True)
    e.start_task(t, T[3], commit=True)
    e.fail_task(t, T[4], commit=True)
    assert e.task_status(t) == T_FAILED


def test_task_fail_retry(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    t = _task(e, wf)
    e.queue_task(t, T[2], commit=True)
    e.start_task(t, T[3], commit=True)
    e.fail_task(t, T[4], commit=True)
    e.queue_task(t, T[5], commit=True)  # FAILED → QUEUED 재시도
    assert e.task_status(t) == T_QUEUED


def test_task_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    t = _task(e, wf)
    # CREATED → COMPLETED 스킵 불가
    with pytest.raises(IllegalTaskTransition):
        e.complete_task(t, T[2], commit=True)


def test_task_block_cancel(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    t = _task(e, wf)
    e.block_task(t, T[2], commit=True)
    assert e.task_status(t) == T_BLOCKED
    e.cancel_task(t, T[3], commit=True)
    assert e.task_status(t) == T_CANCELLED


def test_completed_task_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    t = _task(e, wf)
    e.queue_task(t, T[2], commit=True)
    e.start_task(t, T[3], commit=True)
    e.complete_task(t, T[4], commit=True)
    with pytest.raises(IllegalTaskTransition):
        e.queue_task(t, T[5], commit=True)


def test_task_records_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf)
    assert any(ev["event_type"] == "TASK_CREATED" for ev in ledger.read_events())


@pytest.mark.parametrize("frm,to,ok", [
    (T_CREATED, T_QUEUED, True), (T_CREATED, T_COMPLETED, False), (T_CREATED, T_RUNNING, False),
    (T_QUEUED, T_RUNNING, True), (T_QUEUED, T_COMPLETED, False),
    (T_RUNNING, T_COMPLETED, True), (T_RUNNING, T_FAILED, True), (T_RUNNING, T_BLOCKED, True),
    (T_BLOCKED, T_QUEUED, True), (T_FAILED, T_QUEUED, True),
    (T_COMPLETED, T_QUEUED, False), (T_CANCELLED, T_QUEUED, False),
])
def test_task_transition_matrix(frm, to, ok):
    assert can_task_transition(frm, to) is ok


@pytest.mark.parametrize("s", TASK_STATES)
def test_task_states_in_map(s):
    assert s in ALLOWED_TASK_TRANSITIONS


def test_task_seven_states():
    assert len(TASK_STATES) == 7


# ═══════════════ dependencies / DAG ═══════════════
def test_add_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    b = _task(e, wf, "b")
    d = e.add_dependency(b, a, T[3], commit=True)
    assert d.dependency_id.startswith("WOD:")
    assert d.depends_on == a


def test_dependency_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    with pytest.raises(DanglingDependencyError):
        e.add_dependency(a, "WOT:ghost", T[3], commit=True)


def test_dependency_self_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    with pytest.raises(CircularDependencyError):
        e.add_dependency(a, a, T[3], commit=True)


def test_dependency_cycle_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    b = _task(e, wf, "b")
    e.add_dependency(a, b, T[3], commit=True)
    with pytest.raises(CircularDependencyError):
        e.add_dependency(b, a, T[4], commit=True)


def test_dependency_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    b = _task(e, wf, "b")
    x = e.add_dependency(b, a, T[3], commit=True).dependency_id
    y = e.add_dependency(b, a, T[4], commit=True).dependency_id
    assert x == y
    assert len(ledger.read_dependencies()) == 1


def test_task_order_topological(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    b = _task(e, wf, "b")
    c = _task(e, wf, "c")
    e.add_dependency(b, a, T[3], commit=True)  # b depends on a
    e.add_dependency(c, b, T[4], commit=True)  # c depends on b
    order = e.task_order(wf)
    assert order.index(a) < order.index(b) < order.index(c)


def test_task_order_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf, "a")
    _task(e, wf, "b")
    assert e.task_order(wf) == e.task_order(wf)


def test_detect_cycle():
    assert detect_cycle([("a", "b"), ("b", "a")]) != []
    assert detect_cycle([("a", "b")]) == []


def test_topological_order_cycle_empty():
    assert topological_order(["a", "b"], [("a", "b"), ("b", "a")]) == []


# ═══════════════ execution plan (proposal only) ═══════════════
def test_build_plan_is_proposal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf, "a")
    p = e.build_execution_plan(wf, T[5], commit=True)
    assert p.is_proposal is True
    assert p.plan_id.startswith("WOP:")


def test_plan_resource_duration(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf, "a", meta={"resource": 2, "duration": 5})
    _task(e, wf, "b", meta={"resource": 3, "duration": 7})
    p = e.build_execution_plan(wf, T[5], commit=True)
    assert p.resource_estimate == 5.0
    assert p.expected_duration == 12.0


def test_plan_priority_ordering(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf, "low", prio=1)
    _task(e, wf, "high", prio=9)
    p = e.build_execution_plan(wf, T[5], commit=True)
    high = M.task_id(wf, "high")
    assert p.ordered_tasks[0] == high  # 우선순위 높은 것 먼저


def test_plan_dependency_ready(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    b = _task(e, wf, "b")
    e.add_dependency(b, a, T[3], commit=True)
    p = e.build_execution_plan(wf, T[5], commit=True)
    assert p.dependency_ready is True  # DAG 이므로 위상 정렬 존재


# ═══════════════ runs ═══════════════
def test_start_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf)
    e.ready_workflow(wf, T[2], commit=True)
    r = e.start_run(wf, "", "", T[3], commit=True)
    assert r.run_id.startswith("WOR:")
    assert e.workflow_state(wf) == W_RUNNING


def test_run_records_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running_wf(e)
    assert any(ev["event_type"] == "RUN_STARTED" for ev in ledger.read_events())


def test_multiple_runs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf, t = _running_wf(e)
    e.start_run(wf, "", "", T[5], commit=True)
    assert len(ledger.workflow_runs(wf)) == 2


# ═══════════════ generate_report ═══════════════
def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf, t = _running_wf(e)
    r = e.generate_report(wf, "WORKFLOW", T[5], commit=True)
    assert r.is_binding is False
    assert r.report_id.startswith("WON:")


def test_report_task_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf, "a")
    _task(e, wf, "b")
    r = e.generate_report(wf, "WORKFLOW", T[5], commit=True)
    assert r.task_count == 2
    assert r.task_status_distribution.get("CREATED") == 2


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf, t = _running_wf(e)
    r = e.generate_report(wf, "WORKFLOW", T[5], commit=True)
    assert "EXECUTE" in r.disclaimer


# ═══════════════ event log ═══════════════
@pytest.mark.parametrize("et", EVENT_TYPES)
def test_event_types(et):
    assert et in EVENT_TYPES


def test_event_log_immutable_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf, t = _running_wf(e)
    types = [ev["event_type"] for ev in ledger.workflow_event_log(wf)]
    assert "WORKFLOW_CREATED" in types
    assert "TASK_CREATED" in types
    assert "RUN_STARTED" in types


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_configured():
    for k in ("knowledge_graph", "agent_governance", "decision_intelligence", "simulation",
              "observability"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("di_candidates.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"event_id": f"e{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("decision_intelligence") == 3
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    b = _task(e, wf, "b")
    e.add_dependency(b, a, T[3], commit=True)
    e.ready_workflow(wf, T[4], commit=True)
    e.start_run(wf, "", "", T[5], commit=True)
    e.queue_task(a, T[6], commit=True)
    e.start_task(a, T[7], commit=True)
    e.complete_task(a, T[8], commit=True)
    e.complete_workflow(wf, T[9], commit=True)
    e.generate_report(wf, "WORKFLOW", T[10], commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] > 0


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e)
    p = sp("ro_workflows.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf, "a")
    _task(e, wf, "b")
    p = sp("ro_tasks.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e)
    p = sp("ro_workflows.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_workflow_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running_wf(e)
    assert workflow_lifecycle_integrity()["ok"] is True


def test_task_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    t = _task(e, wf)
    e.queue_task(t, T[2], commit=True)
    assert task_lifecycle_integrity()["ok"] is True


def test_dependency_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    b = _task(e, wf, "b")
    e.add_dependency(b, a, T[3], commit=True)
    assert dependency_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e, "a")
    _wf(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running_wf(e)
    assert reference_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running_wf(e)
    assert lineage_integrity()["ok"] is True


def test_dependency_integrity_detects_dangling(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    a = _task(e, wf, "a")
    b = _task(e, wf, "b")
    e.add_dependency(b, a, T[3], commit=True)
    p = sp("ro_dependencies.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["depends_on"] = "WOT:ghost"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert dependency_integrity()["ok"] is False


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running_wf(e)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["ORCHESTRATE", "PLAN", "SCHEDULE", "TRACK", "RECORD", "REPORT"])
def test_allowed_verb(verb):
    assert is_forbidden_verb(verb) is False


@pytest.mark.parametrize("verb", ["execute_trade", "Place_Order", " deploy_strategy ",
                                   "AUTO_APPROVE", "auto_execute", "change_permission"])
def test_forbidden_normalized(verb):
    assert is_forbidden_verb(verb) is True


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "PROMOTE_MODEL", "CHANGE_PERMISSION",
                                "AUTO_APPROVE", "AUTO_EXECUTE"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert is_forbidden_verb("") is False
    assert is_forbidden_verb(None) is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.workflow_id, ("n",), "WOK:"),
    (M.workflow_event_id, ("w", "S", 0), "WOW:"),
    (M.task_id, ("w", "n"), "WOT:"),
    (M.task_event_id, ("t", "S", 0), "WOS:"),
    (M.dependency_id, ("a", "b"), "WOD:"),
    (M.run_id, ("w", 0), "WOR:"),
    (M.plan_id, ("w", "t"), "WOP:"),
    (M.event_id, ("w", "e", 0), "WOE:"),
    (M.report_id, ("w", "s", "t"), "WON:"),
    (M.artifact_id, ("WORKFLOW", "r"), "WOF:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ 조회 ═══════════════
def test_list_workflows(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e, "a")
    _wf(e, "b")
    assert len(e.list_workflows()) == 2


def test_workflows_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _task(e, wf)
    assert wf in e.workflows_in_state(W_DEFINED)


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf, t = _running_wf(e)
    s = e.summary(T[9])
    assert s.workflow_event_count >= 3
    assert s.task_event_count >= 1
    assert s.run_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_operations.__main__ import main
    assert main(["workflow", "--name", "w", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["workflow"]["to_state"] == W_DRAFT


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_operations.__main__ import main
    main(["workflow", "--name", "w", "--commit"])
    wf = json.loads(capsys.readouterr().out)["workflow"]["workflow_id"]
    main(["task", "--workflow", wf, "--name", "a", "--commit"])
    ta = json.loads(capsys.readouterr().out)["task"]["task_id"]
    main(["ready", "--workflow", wf, "--commit"])
    capsys.readouterr()
    main(["run", "--workflow", wf, "--commit"])
    capsys.readouterr()
    assert main(["report", "--workflow", wf, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_operations.__main__ import main
    assert main(["verify"]) == 0


def test_cli_workflows(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_operations.__main__ import main
    main(["workflow", "--name", "w", "--commit"])
    capsys.readouterr()
    assert main(["workflows"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["workflows"]) == 1


def test_cli_plan_and_order(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_operations.__main__ import main
    main(["workflow", "--name", "w", "--commit"])
    wf = json.loads(capsys.readouterr().out)["workflow"]["workflow_id"]
    main(["task", "--workflow", wf, "--name", "a", "--commit"])
    a = json.loads(capsys.readouterr().out)["task"]["task_id"]
    main(["task", "--workflow", wf, "--name", "b", "--commit"])
    b = json.loads(capsys.readouterr().out)["task"]["task_id"]
    main(["depend", "--task", b, "--on", a, "--commit"])
    capsys.readouterr()
    assert main(["order", "--workflow", wf]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["task_order"].index(a) < out["task_order"].index(b)


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_operations.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_operations.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / 불변 ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_workflow("w", "d", T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "ro_workflows.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_workflow("w", "d", T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"


def test_eight_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("ro_")


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.live_execution", "jarvis.live_trading",
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
    bad = ("execute_trade", "place_order", "allocate_capital", "deploy_strategy", "deploy_model",
           "promote_model", "change_permission", "grant_permission", "auto_approve",
           "auto_execute", "auto_deploy", "auto_trade")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_delete_update_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def update_", "def remove_", "def overwrite_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


# ═══════════════ end-to-end (research pipeline) ═══════════════
def test_end_to_end_pipeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = e.create_workflow("strategy-study", "hypothesis→experiment→backtest→validation→sim→report",
                           T[0], commit=True).workflow_id
    hypo = e.add_task(wf, "hypothesis", "d", "alice", 5, {"resource": 1, "duration": 2}, T[1],
                      commit=True).task_id
    exp = e.add_task(wf, "experiment", "d", "bob", 4, {"resource": 2, "duration": 4}, T[2],
                     commit=True).task_id
    bt = e.add_task(wf, "backtest", "d", "carol", 3, {"resource": 3, "duration": 6}, T[3],
                    commit=True).task_id
    val = e.add_task(wf, "validation", "d", "dave", 2, {}, T[4], commit=True).task_id
    sim = e.add_task(wf, "simulation", "d", "erin", 1, {}, T[5], commit=True).task_id
    rep = e.add_task(wf, "decision_report", "d", "frank", 0, {}, T[6], commit=True).task_id
    e.add_dependency(exp, hypo, T[7], commit=True)
    e.add_dependency(bt, exp, T[8], commit=True)
    e.add_dependency(val, bt, T[9], commit=True)
    e.add_dependency(sim, val, T[10], commit=True)
    e.add_dependency(rep, sim, T[11], commit=True)
    order = e.task_order(wf)
    assert order.index(hypo) < order.index(exp) < order.index(bt) < order.index(val) \
        < order.index(sim) < order.index(rep)
    plan = e.build_execution_plan(wf, T[12], commit=True)
    assert plan.is_proposal is True
    assert plan.expected_duration == 12.0
    e.ready_workflow(wf, T[13], commit=True)
    e.start_run(wf, plan.plan_id, "run1", T[14], commit=True)
    assert e.workflow_state(wf) == W_RUNNING
    e.queue_task(hypo, T[15], commit=True)
    e.start_task(hypo, T[16], commit=True)
    e.complete_task(hypo, T[17], commit=True)
    e.complete_workflow(wf, T[18], commit=True)
    r = e.generate_report(wf, "WORKFLOW", T[19], commit=True)
    assert r.task_count == 6
    assert r.is_binding is False
    e.archive_workflow(wf, T[20], commit=True)
    assert e.workflow_state(wf) == W_ARCHIVED
    assert verify_chain()["ok"] is True
    assert replay(e, T[21])["deterministic"] is True
