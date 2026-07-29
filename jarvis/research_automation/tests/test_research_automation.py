"""P22 research_automation 테스트 — 워크플로/파이프라인/작업 생애주기·의존 DAG·순환·런·리포트·
계보·verify·replay·CLI·보안·금지능력·READ ONLY 상위·결정성."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_automation import ledger
from jarvis.research_automation import models as M
from jarvis.research_automation.engine import ResearchAutomationEngine
from jarvis.research_automation.models import (
    EVENT_TYPES,
    FORBIDDEN_VERBS,
    GENESIS,
    PIPELINE_STATES,
    P_CREATED,
    P_EXECUTING,
    P_FINISHED,
    P_READY,
    TASK_STATES,
    T_ARCHIVED,
    T_COMPLETED,
    T_CREATED,
    T_FAILED,
    T_QUEUED,
    T_RUNNING,
    WORKFLOW_STATES,
    W_ACTIVE,
    W_ARCHIVED,
    W_COMPLETED,
    W_DRAFT,
    W_RUNNING,
    CircularDependencyError,
    DanglingDependencyError,
    IllegalPipelineTransition,
    IllegalTaskTransition,
    IllegalWorkflowTransition,
    ImmutableWorkflowError,
    UnknownEntityError,
    can_pipeline_transition,
    can_task_transition,
    can_workflow_transition,
    content_hash,
    detect_cycle,
    topological_order,
)
from jarvis.research_automation.verify import (
    dependency_integrity,
    duplicate_integrity,
    lifecycle_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_automation.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchAutomationEngine()


def _wf(e, name="wf1", ver="1.0", now=T[0]):
    return e.register_workflow(name, ver, "desc", ["alpha_intelligence"], now, commit=True).workflow_id


def _pipe(e, wf, name="p1", now=T[1]):
    return e.define_pipeline(wf, name, ["step1"], now, commit=True).pipeline_id


def _task(e, pipe, name="t1", now=T[2]):
    return e.create_task(pipe, name, "research", "ai:sig1", now, commit=True).task_id


# ═══════════════ workflow lifecycle ═══════════════
def test_register_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_workflow("wf", "1.0", "d", [], T[0], commit=True)
    assert ev.to_state == W_DRAFT
    assert ev.workflow_id.startswith("RAW:")
    assert ev.workflow_event_id.startswith("RAK:")


def test_workflow_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_workflow("wf", "1.0", "d", [], T[0], commit=True).workflow_id
    b = e.register_workflow("wf", "1.0", "d", [], T[1], commit=True).workflow_id
    assert a == b
    assert len(ledger.workflow_events(a)) == 1


def test_workflow_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_workflow("wf", "1.0", "d1", [], T[0], commit=True)
    with pytest.raises(ImmutableWorkflowError):
        e.register_workflow("wf", "1.0", "d2", [], T[1], commit=True)


def test_workflow_version_distinct(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_workflow("wf", "1.0", "d", [], T[0], commit=True).workflow_id
    b = e.register_workflow("wf", "2.0", "d", [], T[1], commit=True).workflow_id
    assert a != b


def test_workflow_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    e.activate_workflow(wf, T[1], commit=True)
    e.run_workflow(wf, T[2], commit=True)
    e.complete_workflow(wf, T[3], commit=True)
    e.archive_workflow(wf, T[4], commit=True)
    assert e.workflow_state(wf) == W_ARCHIVED


def test_workflow_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    with pytest.raises(IllegalWorkflowTransition):
        e.run_workflow(wf, T[1], commit=True)  # DRAFT→RUNNING skip


def test_workflow_records_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e)
    assert any(ev["event_type"] == "WORKFLOW_REGISTERED" for ev in ledger.read_events())


def test_workflow_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e)
    assert any(a["artifact_type"] == "WORKFLOW" for a in ledger.read_artifacts())


@pytest.mark.parametrize("frm,to,ok", [
    (W_DRAFT, W_ACTIVE, True), (W_DRAFT, W_RUNNING, False),
    (W_ACTIVE, W_RUNNING, True), (W_RUNNING, W_COMPLETED, True),
    (W_COMPLETED, W_ARCHIVED, True), (W_ARCHIVED, W_ACTIVE, False),
])
def test_workflow_transition_matrix(frm, to, ok):
    assert can_workflow_transition(frm, to) is ok


@pytest.mark.parametrize("s", WORKFLOW_STATES)
def test_workflow_states(s):
    assert s in WORKFLOW_STATES


# ═══════════════ pipeline lifecycle ═══════════════
def test_define_pipeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    p = e.define_pipeline(wf, "p1", ["s1", "s2"], T[1], commit=True)
    assert p.pipeline_id.startswith("RAP:")
    assert p.to_state == P_CREATED


def test_pipeline_activates_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _pipe(e, wf)
    assert e.workflow_state(wf) == W_ACTIVE


def test_pipeline_ready_requires_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    with pytest.raises(IllegalPipelineTransition):
        e.ready_pipeline(pipe, T[3], commit=True)


def test_pipeline_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe)
    e.ready_pipeline(pipe, T[3], commit=True)
    e.start_research_run(pipe, "", T[4], commit=True)
    assert e.pipeline_state(pipe) == P_EXECUTING
    e.finish_pipeline(pipe, T[5], commit=True)
    assert e.pipeline_state(pipe) == P_FINISHED


def test_pipeline_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe)
    with pytest.raises(IllegalPipelineTransition):
        e.finish_pipeline(pipe, T[3], commit=True)  # CREATED→FINISHED skip


@pytest.mark.parametrize("frm,to,ok", [
    (P_CREATED, P_READY, True), (P_CREATED, P_EXECUTING, False),
    (P_READY, P_EXECUTING, True), (P_EXECUTING, P_FINISHED, True), (P_FINISHED, P_READY, False),
])
def test_pipeline_transition_matrix(frm, to, ok):
    assert can_pipeline_transition(frm, to) is ok


@pytest.mark.parametrize("s", PIPELINE_STATES)
def test_pipeline_states(s):
    assert s in PIPELINE_STATES


# ═══════════════ task lifecycle ═══════════════
def test_create_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    t = e.create_task(pipe, "alpha_discovery", "alpha", "ai:sig", T[2], commit=True)
    assert t.task_id.startswith("RAT:")
    assert t.to_state == T_CREATED
    assert t.task_type == "alpha"


def test_task_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    t = _task(e, pipe)
    e.queue_task(t, T[3], commit=True)
    e.start_task(t, T[4], commit=True)
    e.record_task_result(t, "COMPLETED", {"score": 0.7}, T[5], commit=True)
    assert e.task_state(t) == T_COMPLETED


def test_task_result_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    t = _task(e, pipe)
    e.queue_task(t, T[3], commit=True)
    e.start_task(t, T[4], commit=True)
    e.record_task_result(t, "FAILED", {"error": "x"}, T[5], commit=True)
    assert e.task_state(t) == T_FAILED


def test_task_failed_retry(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    t = _task(e, pipe)
    e.queue_task(t, T[3], commit=True)
    e.start_task(t, T[4], commit=True)
    e.record_task_result(t, "FAILED", {}, T[5], commit=True)
    e.queue_task(t, T[6], commit=True)  # FAILED→QUEUED retry
    assert e.task_state(t) == T_QUEUED


def test_task_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    t = _task(e, pipe)
    with pytest.raises(IllegalTaskTransition):
        e.record_task_result(t, "COMPLETED", {}, T[3], commit=True)  # CREATED→COMPLETED skip


def test_task_add_after_executing_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe)
    e.ready_pipeline(pipe, T[3], commit=True)
    e.start_research_run(pipe, "", T[4], commit=True)
    with pytest.raises(IllegalPipelineTransition):
        e.create_task(pipe, "late", now=T[5], commit=True)


def test_task_records_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    t = _task(e, pipe)
    e.queue_task(t, T[3], commit=True)
    e.start_task(t, T[4], commit=True)
    ev = e.record_task_result(t, "COMPLETED", {"sharpe": 1.5}, T[5], commit=True)
    assert ev.results == {"sharpe": 1.5}


@pytest.mark.parametrize("frm,to,ok", [
    (T_CREATED, T_QUEUED, True), (T_CREATED, T_RUNNING, False),
    (T_QUEUED, T_RUNNING, True), (T_RUNNING, T_COMPLETED, True), (T_RUNNING, T_FAILED, True),
    (T_COMPLETED, T_ARCHIVED, True), (T_FAILED, T_QUEUED, True), (T_ARCHIVED, T_QUEUED, False),
])
def test_task_transition_matrix(frm, to, ok):
    assert can_task_transition(frm, to) is ok


@pytest.mark.parametrize("s", TASK_STATES)
def test_task_states(s):
    assert s in TASK_STATES


# ═══════════════ dependencies / DAG ═══════════════
def test_add_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    a = _task(e, pipe, "a")
    b = _task(e, pipe, "b")
    d = e.add_dependency(a, b, "requires", T[3], commit=True)
    assert d.dependency_id.startswith("RAD:")
    assert d.parent_task == a


def test_dependency_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    a = _task(e, pipe, "a")
    with pytest.raises(DanglingDependencyError):
        e.add_dependency(a, "RAT:ghost", "requires", T[3], commit=True)


def test_dependency_self_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    a = _task(e, pipe, "a")
    with pytest.raises(CircularDependencyError):
        e.add_dependency(a, a, "requires", T[3], commit=True)


def test_dependency_cycle_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    a = _task(e, pipe, "a")
    b = _task(e, pipe, "b")
    e.add_dependency(a, b, "requires", T[3], commit=True)  # b depends on a
    with pytest.raises(CircularDependencyError):
        e.add_dependency(b, a, "requires", T[4], commit=True)  # a depends on b → cycle


def test_resolve_dependencies_order(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    a = _task(e, pipe, "a")
    b = _task(e, pipe, "b")
    c = _task(e, pipe, "c")
    e.add_dependency(a, b, "requires", T[3], commit=True)  # b after a
    e.add_dependency(b, c, "requires", T[4], commit=True)  # c after b
    res = e.resolve_dependencies(pipe)
    order = res["order"]
    assert order.index(a) < order.index(b) < order.index(c)
    assert res["cycle"] == []
    assert res["resolved"] is True


def test_resolve_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe, "a")
    _task(e, pipe, "b")
    assert e.resolve_dependencies(pipe) == e.resolve_dependencies(pipe)


def test_detect_cycle():
    assert detect_cycle([("a", "b"), ("b", "a")]) != []
    assert detect_cycle([("a", "b")]) == []


def test_topological_order_cycle():
    assert topological_order(["a", "b"], [("a", "b"), ("b", "a")]) == []


# ═══════════════ runs ═══════════════
def test_start_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe)
    e.ready_pipeline(pipe, T[3], commit=True)
    r = e.start_research_run(pipe, "run1", T[4], commit=True)
    assert r.run_id.startswith("RAR:")
    assert e.pipeline_state(pipe) == P_EXECUTING
    assert e.workflow_state(wf) == W_RUNNING


def test_run_records_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe)
    e.ready_pipeline(pipe, T[3], commit=True)
    e.start_research_run(pipe, "", T[4], commit=True)
    assert any(ev["event_type"] == "RUN_STARTED" for ev in ledger.read_events())


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe, "a")
    _task(e, pipe, "b")
    r = e.generate_report(pipe, "PIPELINE", T[5], commit=True)
    assert r.report_id.startswith("RAF:")
    assert r.is_binding is False
    assert r.task_count == 2
    assert r.task_status_distribution.get("CREATED") == 2


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    r = e.generate_report(pipe, "PIPELINE", T[5], commit=True)
    assert "VALIDATED" in r.disclaimer


# ═══════════════ event types ═══════════════
@pytest.mark.parametrize("et", EVENT_TYPES)
def test_event_types(et):
    assert et in EVENT_TYPES


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers(tmp_path, monkeypatch):
    for k in ("research_governance", "alpha_intelligence", "portfolio_research", "knowledge_graph",
              "agent_governance", "decision_intelligence", "simulation"):
        assert k in ledger.SOURCE_LAYERS


def test_source_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("ai_signals.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"signal_hash": f"s{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("alpha_intelligence") == 3
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    a = _task(e, pipe, "a")
    b = _task(e, pipe, "b")
    e.add_dependency(a, b, "requires", T[3], commit=True)
    e.ready_pipeline(pipe, T[4], commit=True)
    e.start_research_run(pipe, "", T[5], commit=True)
    e.queue_task(a, T[6], commit=True)
    e.start_task(a, T[7], commit=True)
    e.record_task_result(a, "COMPLETED", {"x": 1}, T[8], commit=True)
    e.finish_pipeline(pipe, T[9], commit=True)
    e.generate_report(pipe, "PIPELINE", T[10], commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] > 0


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _wf(e)
    p = sp("ra_workflows.jsonl")
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
    pipe = _pipe(e, wf)
    _task(e, pipe, "a")
    _task(e, pipe, "b")
    p = sp("ra_tasks.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate_execution(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe)
    e.ready_pipeline(pipe, T[3], commit=True)
    e.start_research_run(pipe, "", T[4], commit=True)
    p = sp("ra_runs.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe)
    assert lifecycle_integrity()["ok"] is True


def test_dependency_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    a = _task(e, pipe, "a")
    b = _task(e, pipe, "b")
    e.add_dependency(a, b, "requires", T[3], commit=True)
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
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe)
    assert reference_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _pipe(e, wf)
    assert lineage_integrity()["ok"] is True


def test_dependency_integrity_detects_missing(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    a = _task(e, pipe, "a")
    b = _task(e, pipe, "b")
    e.add_dependency(a, b, "requires", T[3], commit=True)
    p = sp("ra_dependencies.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["parent_task"] = "RAT:ghost"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert dependency_integrity()["ok"] is False


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    _pipe(e, wf)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["ORCHESTRATE", "SCHEDULE", "RESOLVE", "TRACK", "REPORT"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "PROMOTE_MODEL", "ENABLE_LIVE", "ACTIVATE_LIVE",
                                "PORTFOLIO_MUTATION", "AUTO_SELECT_STRATEGY", "AUTO_APPROVE_ALPHA",
                                "AUTO_DEPLOY_PORTFOLIO", "AUTO_CHANGE_PERMISSIONS"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.workflow_id, ("n", "1"), "RAW:"),
    (M.workflow_event_id, ("w", "S", 0), "RAK:"),
    (M.pipeline_id, ("w", "n"), "RAP:"),
    (M.pipeline_event_id, ("p", "S", 0), "RAG:"),
    (M.task_id, ("p", "n"), "RAT:"),
    (M.task_event_id, ("t", "S", 0), "RAN:"),
    (M.run_id, ("p", 0), "RAR:"),
    (M.dependency_id, ("a", "b"), "RAD:"),
    (M.event_id, ("s", "e", 0), "RAM:"),
    (M.report_id, ("p", "s", "t"), "RAF:"),
    (M.artifact_id, ("WORKFLOW", "r"), "RAA:"),
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


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    wf = _wf(e)
    pipe = _pipe(e, wf)
    _task(e, pipe)
    s = e.summary(T[9])
    assert s.workflow_event_count >= 1
    assert s.pipeline_event_count >= 1
    assert s.task_event_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_automation.__main__ import main
    assert main(["workflow", "--name", "w", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["workflow"]["to_state"] == W_DRAFT


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_automation.__main__ import main
    main(["workflow", "--name", "w", "--commit"])
    wf = json.loads(capsys.readouterr().out)["workflow"]["workflow_id"]
    main(["pipeline", "--workflow", wf, "--name", "p", "--commit"])
    pipe = json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"]
    main(["task", "--pipeline", pipe, "--name", "t", "--commit"])
    capsys.readouterr()
    assert main(["report", "--pipeline", pipe, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_automation.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_automation.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_automation.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


def test_cli_dependency(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_automation.__main__ import main
    main(["workflow", "--name", "w", "--commit"])
    wf = json.loads(capsys.readouterr().out)["workflow"]["workflow_id"]
    main(["pipeline", "--workflow", wf, "--name", "p", "--commit"])
    pipe = json.loads(capsys.readouterr().out)["pipeline"]["pipeline_id"]
    main(["task", "--pipeline", pipe, "--name", "a", "--commit"])
    a = json.loads(capsys.readouterr().out)["task"]["task_id"]
    main(["task", "--pipeline", pipe, "--name", "b", "--commit"])
    b = json.loads(capsys.readouterr().out)["task"]["task_id"]
    assert main(["dependency", "--parent", a, "--child", b, "--commit"]) == 0


# ═══════════════ 격리 / ledger ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_workflow("w", "1.0", "d", [], T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "ra_workflows.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_workflow("w", "1.0", "d", [], T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"


def test_eight_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("ra_")


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio_live", "jarvis.permission_control",
    "jarvis.risk_execution", "jarvis.portfolio", "jarvis.risk", "jarvis.permission",
    "jarvis.deployment", "jarvis.live", "jarvis.order", "jarvis.live_execution",
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
    bad = ("execute_trade", "place_order", "allocate_capital", "deploy_strategy", "promote_model",
           "enable_live", "activate_live", "portfolio_mutation", "auto_select_strategy",
           "auto_approve_alpha", "auto_deploy_portfolio", "auto_change_permissions")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def update_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


# ═══════════════ end-to-end (research pipeline) ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    # alpha discovery → signal eval → portfolio study → simulation → decision
    wf = e.register_workflow("alpha-pipeline", "1.0", "e2e", ["alpha_intelligence", "simulation"],
                             T[0], commit=True).workflow_id
    pipe = e.define_pipeline(wf, "main", ["discover", "eval", "portfolio", "sim", "decision"],
                             T[1], commit=True).pipeline_id
    disc = e.create_task(pipe, "alpha_discovery", "alpha", "ai:sig", T[2], commit=True).task_id
    ev = e.create_task(pipe, "signal_eval", "eval", "ai:sig", T[3], commit=True).task_id
    port = e.create_task(pipe, "portfolio_study", "portfolio", "pr:port", T[4], commit=True).task_id
    sim = e.create_task(pipe, "simulation_validation", "sim", "sim:sc", T[5], commit=True).task_id
    dec = e.create_task(pipe, "decision_comparison", "decision", "di:cand", T[6], commit=True).task_id
    e.add_dependency(disc, ev, "requires", T[7], commit=True)
    e.add_dependency(ev, port, "requires", T[8], commit=True)
    e.add_dependency(port, sim, "requires", T[9], commit=True)
    e.add_dependency(sim, dec, "requires", T[10], commit=True)
    res = e.resolve_dependencies(pipe)
    order = res["order"]
    assert order.index(disc) < order.index(ev) < order.index(port) < order.index(sim) \
        < order.index(dec)
    assert res["cycle"] == []
    e.ready_pipeline(pipe, T[11], commit=True)
    e.start_research_run(pipe, "run", T[12], commit=True)
    assert e.workflow_state(wf) == W_RUNNING
    for t in (disc, ev, port, sim, dec):
        e.queue_task(t, T[13], commit=True)
        e.start_task(t, T[14], commit=True)
        e.record_task_result(t, "COMPLETED", {"ok": True}, T[15], commit=True)
    e.finish_pipeline(pipe, T[16], commit=True)
    e.complete_workflow(wf, T[17], commit=True)
    r = e.generate_report(pipe, "PIPELINE", T[18], commit=True)
    assert r.task_count == 5
    assert r.task_status_distribution.get("COMPLETED") == 5
    assert r.is_binding is False  # COMPLETED ≠ VALIDATED
    e.archive_workflow(wf, T[19], commit=True)
    assert e.workflow_state(wf) == W_ARCHIVED
    assert verify_chain()["ok"] is True
    assert replay(e, T[20])["deterministic"] is True
