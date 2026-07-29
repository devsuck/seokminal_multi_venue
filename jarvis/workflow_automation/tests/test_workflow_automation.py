"""Workflow Automation Layer(P44) 테스트 — 워크플로/태스크 생애주기·의존성·검토·검증·재현·안전.

**자율 실행 없음 — 사람 승인 필수.** 격리 원장(tmp)에서 실행: state_path 몽키패치.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.workflow_automation import ledger
from jarvis.workflow_automation import models as M
from jarvis.workflow_automation.engine import WorkflowAutomationEngine
from jarvis.workflow_automation.models import (
    DependencyCycleError,
    IllegalTaskTransition,
    IllegalWorkflowTransition,
    UnknownEntityError,
)
from jarvis.workflow_automation.verify import (
    approval_integrity,
    dependency_integrity,
    duplicate_integrity,
    lineage_integrity,
    replay,
    task_lifecycle_integrity,
    verify_chain,
    workflow_lifecycle_integrity,
)

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
# 모델 식별자 리터럴 유출 회피용 토큰
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


@pytest.fixture()
def eng(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    return WorkflowAutomationEngine()


# ──────────────────────── 워크플로 생애주기 ────────────────────────
def test_create_workflow_genesis(eng):
    ev = eng.create_workflow("alpha", "연구 워크플로", NOW, commit=True)
    assert ev.from_state == M.GENESIS
    assert ev.to_state == M.W_CREATED
    assert ev.workflow_id.startswith("WFW:")


def test_create_workflow_idempotent(eng):
    a = eng.create_workflow("alpha", "d", NOW, commit=True)
    b = eng.create_workflow("alpha", "d", NOW, commit=True)
    assert a.workflow_id == b.workflow_id
    assert len(ledger.workflow_ids()) == 1


def test_create_workflow_no_commit_not_persisted(eng):
    eng.create_workflow("alpha", "d", NOW, commit=False)
    assert ledger.workflow_ids() == []


def test_workflow_state_initial(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    assert eng.workflow_state(wf) == M.W_CREATED


def test_advance_to_planned(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    ev = eng.advance_state(wf, M.W_PLANNED, "", NOW, commit=True)
    assert ev.to_state == M.W_PLANNED
    assert eng.workflow_state(wf) == M.W_PLANNED


def test_full_workflow_lifecycle(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.plan_workflow(wf, now=NOW, commit=True)
    eng.start_workflow(wf, now=NOW, commit=True)
    eng.complete_workflow(wf, now=NOW, commit=True)
    eng.archive_workflow(wf, now=NOW, commit=True)
    assert eng.workflow_state(wf) == M.W_ARCHIVED


def test_running_self_loop(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.plan_workflow(wf, now=NOW, commit=True)
    eng.start_workflow(wf, now=NOW, commit=True)
    eng.advance_state(wf, M.W_RUNNING, "progress", NOW, commit=True)
    assert eng.workflow_state(wf) == M.W_RUNNING


def test_illegal_skip_transition(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    with pytest.raises(IllegalWorkflowTransition):
        eng.advance_state(wf, M.W_RUNNING, "", NOW, commit=True)


def test_illegal_created_to_completed(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    with pytest.raises(IllegalWorkflowTransition):
        eng.advance_state(wf, M.W_COMPLETED, "", NOW, commit=True)


def test_archived_is_terminal(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.plan_workflow(wf, now=NOW, commit=True)
    eng.start_workflow(wf, now=NOW, commit=True)
    eng.complete_workflow(wf, now=NOW, commit=True)
    eng.archive_workflow(wf, now=NOW, commit=True)
    with pytest.raises(IllegalWorkflowTransition):
        eng.advance_state(wf, M.W_RUNNING, "", NOW, commit=True)


def test_advance_unknown_workflow(eng):
    with pytest.raises(UnknownEntityError):
        eng.advance_state("WFW:deadbeef", M.W_PLANNED, "", NOW, commit=True)


def test_advance_invalid_state_value(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    with pytest.raises(ValueError):
        eng.advance_state(wf, "NONSENSE", "", NOW, commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (M.W_CREATED, M.W_PLANNED, True),
    (M.W_CREATED, M.W_RUNNING, False),
    (M.W_CREATED, M.W_COMPLETED, False),
    (M.W_PLANNED, M.W_RUNNING, True),
    (M.W_PLANNED, M.W_COMPLETED, False),
    (M.W_RUNNING, M.W_RUNNING, True),
    (M.W_RUNNING, M.W_COMPLETED, True),
    (M.W_RUNNING, M.W_PLANNED, False),
    (M.W_COMPLETED, M.W_ARCHIVED, True),
    (M.W_COMPLETED, M.W_RUNNING, False),
    (M.W_ARCHIVED, M.W_ARCHIVED, False),
    (M.W_ARCHIVED, M.W_PLANNED, False),
])
def test_workflow_transition_matrix(frm, to, ok):
    assert M.can_workflow_transition(frm, to) is ok


# ──────────────────────── 태스크 ────────────────────────
def test_add_task_genesis(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    t = eng.add_task(wf, "collect", "DATA_PREP", NOW, commit=True)
    assert t.from_state == M.GENESIS
    assert t.to_state == M.T_PENDING
    assert t.task_id.startswith("WFT:")
    assert t.kind == "DATA_PREP"


def test_add_task_idempotent(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    a = eng.add_task(wf, "collect", now=NOW, commit=True)
    b = eng.add_task(wf, "collect", now=NOW, commit=True)
    assert a.task_id == b.task_id
    assert len(ledger.task_ids_for(wf)) == 1


def test_add_task_unknown_workflow(eng):
    with pytest.raises(UnknownEntityError):
        eng.add_task("WFW:deadbeef", "collect", now=NOW, commit=True)


def test_add_task_bad_kind(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    with pytest.raises(ValueError):
        eng.add_task(wf, "collect", "NONSENSE", NOW, commit=True)


def test_task_lifecycle(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.add_task(wf, "collect", now=NOW, commit=True)
    tsk = M.task_id(wf, "collect")
    eng.advance_task(tsk, M.T_READY, now=NOW, commit=True)
    eng.advance_task(tsk, M.T_RUNNING, now=NOW, commit=True)
    eng.advance_task(tsk, M.T_COMPLETED, now=NOW, commit=True)
    assert eng.task_state(tsk) == M.T_COMPLETED


def test_task_block_and_unblock(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.add_task(wf, "collect", now=NOW, commit=True)
    tsk = M.task_id(wf, "collect")
    eng.advance_task(tsk, M.T_BLOCKED, now=NOW, commit=True)
    assert eng.task_state(tsk) == M.T_BLOCKED
    eng.advance_task(tsk, M.T_READY, now=NOW, commit=True)
    assert eng.task_state(tsk) == M.T_READY


def test_task_illegal_transition(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.add_task(wf, "collect", now=NOW, commit=True)
    tsk = M.task_id(wf, "collect")
    with pytest.raises(IllegalTaskTransition):
        eng.advance_task(tsk, M.T_COMPLETED, now=NOW, commit=True)


def test_task_completed_terminal(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.add_task(wf, "collect", now=NOW, commit=True)
    tsk = M.task_id(wf, "collect")
    eng.advance_task(tsk, M.T_READY, now=NOW, commit=True)
    eng.advance_task(tsk, M.T_RUNNING, now=NOW, commit=True)
    eng.advance_task(tsk, M.T_COMPLETED, now=NOW, commit=True)
    with pytest.raises(IllegalTaskTransition):
        eng.advance_task(tsk, M.T_RUNNING, now=NOW, commit=True)


def test_advance_unknown_task(eng):
    with pytest.raises(UnknownEntityError):
        eng.advance_task("WFT:deadbeef", M.T_READY, now=NOW, commit=True)


def test_task_bad_state_value(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.add_task(wf, "collect", now=NOW, commit=True)
    tsk = M.task_id(wf, "collect")
    with pytest.raises(ValueError):
        eng.advance_task(tsk, "NONSENSE", now=NOW, commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (M.T_PENDING, M.T_READY, True),
    (M.T_PENDING, M.T_BLOCKED, True),
    (M.T_PENDING, M.T_RUNNING, False),
    (M.T_PENDING, M.T_COMPLETED, False),
    (M.T_READY, M.T_RUNNING, True),
    (M.T_READY, M.T_BLOCKED, True),
    (M.T_READY, M.T_COMPLETED, False),
    (M.T_RUNNING, M.T_COMPLETED, True),
    (M.T_RUNNING, M.T_RUNNING, True),
    (M.T_RUNNING, M.T_BLOCKED, True),
    (M.T_BLOCKED, M.T_READY, True),
    (M.T_BLOCKED, M.T_PENDING, True),
    (M.T_BLOCKED, M.T_COMPLETED, False),
    (M.T_COMPLETED, M.T_RUNNING, False),
    (M.T_COMPLETED, M.T_READY, False),
])
def test_task_transition_matrix(frm, to, ok):
    assert M.can_task_transition(frm, to) is ok


@pytest.mark.parametrize("kind", list(M.TASK_KINDS))
def test_all_task_kinds(eng, kind):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    t = eng.add_task(wf, f"task-{kind}", kind, NOW, commit=True)
    assert t.kind == kind


def test_multiple_tasks_in_workflow(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    for n in ("a", "b", "c", "d"):
        eng.add_task(wf, n, now=NOW, commit=True)
    assert len(ledger.task_ids_for(wf)) == 4


# ──────────────────────── 의존성 ────────────────────────
def _wf_with_tasks(eng, names):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    for n in names:
        eng.add_task(wf, n, now=NOW, commit=True)
    return wf, {n: M.task_id(wf, n) for n in names}


def test_track_dependency(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    d = eng.track_dependency(wf, t["a"], t["b"], NOW, commit=True)
    assert d.from_task == t["a"]
    assert d.to_task == t["b"]
    assert d.dependency_id.startswith("WFD:")


def test_dependency_idempotent(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    d1 = eng.track_dependency(wf, t["a"], t["b"], NOW, commit=True)
    d2 = eng.track_dependency(wf, t["a"], t["b"], NOW, commit=True)
    assert d1.dependency_id == d2.dependency_id
    assert len(ledger.dependencies_for(wf)) == 1


def test_self_dependency_blocked(eng):
    wf, t = _wf_with_tasks(eng, ["a"])
    with pytest.raises(DependencyCycleError):
        eng.track_dependency(wf, t["a"], t["a"], NOW, commit=True)


def test_dependency_cycle_blocked(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b", "c"])
    eng.track_dependency(wf, t["a"], t["b"], NOW, commit=True)
    eng.track_dependency(wf, t["b"], t["c"], NOW, commit=True)
    with pytest.raises(DependencyCycleError):
        eng.track_dependency(wf, t["c"], t["a"], NOW, commit=True)


def test_dependency_unknown_task(eng):
    wf, t = _wf_with_tasks(eng, ["a"])
    with pytest.raises(UnknownEntityError):
        eng.track_dependency(wf, t["a"], "WFT:deadbeef", NOW, commit=True)


def test_dependency_no_commit(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    eng.track_dependency(wf, t["a"], t["b"], NOW, commit=False)
    assert ledger.dependencies_for(wf) == []


def test_execution_order(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b", "c"])
    # c depends on b, b depends on a  → order a, b, c
    eng.track_dependency(wf, t["b"], t["a"], NOW, commit=True)
    eng.track_dependency(wf, t["c"], t["b"], NOW, commit=True)
    order = eng.task_execution_order(wf)
    assert order.index(t["a"]) < order.index(t["b"]) < order.index(t["c"])


def test_execution_order_no_deps(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    order = eng.task_execution_order(wf)
    assert set(order) == {t["a"], t["b"]}


def test_topological_order_cycle_none():
    nodes = ["a", "b"]
    edges = [("a", "b"), ("b", "a")]
    assert M.topological_order(nodes, edges) is None


def test_topological_order_deterministic():
    nodes = ["x", "y", "z"]
    edges = [("y", "x"), ("z", "y")]
    o1 = M.topological_order(nodes, edges)
    o2 = M.topological_order(nodes, edges)
    assert o1 == o2 == ["x", "y", "z"]


# ──────────────────────── 검토 요청(사람 승인 필수) ────────────────────────
def test_request_review(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    a = eng.request_review(wf, "PRE_RUN", "검토 요망", NOW, commit=True)
    assert a.status == M.REVIEW_PENDING
    assert a.is_granted is False
    assert a.requires_human_approval is True


def test_review_never_auto_granted(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    for stage in ("A", "B", "C"):
        eng.request_review(wf, stage, "", NOW, commit=True)
    assert all(a["is_granted"] is False for a in ledger.read_approvals())
    assert approval_integrity()["ok"]


def test_engine_has_no_approve_method(eng):
    assert not hasattr(eng, "approve")
    assert not hasattr(eng, "grant")
    assert not hasattr(eng, "grant_approval")


def test_multiple_reviews_same_stage(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    a1 = eng.request_review(wf, "PRE_RUN", "", NOW, commit=True)
    a2 = eng.request_review(wf, "PRE_RUN", "", NOW, commit=True)
    assert a1.approval_id != a2.approval_id
    assert len(ledger.approvals_for(wf)) == 2


# ──────────────────────── 메타데이터 ────────────────────────
def test_record_metadata(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    m = eng.record_metadata(wf, "owner", "research-team", NOW, commit=True)
    assert m.key == "owner"
    assert m.value == "research-team"


def test_metadata_idempotent(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    m1 = eng.record_metadata(wf, "owner", "x", NOW, commit=True)
    m2 = eng.record_metadata(wf, "owner", "y", NOW, commit=True)
    assert m1.metadata_id == m2.metadata_id
    assert m1.value == m2.value == "x"


def test_metadata_unknown_workflow(eng):
    with pytest.raises(UnknownEntityError):
        eng.record_metadata("WFW:deadbeef", "k", "v", NOW, commit=True)


# ──────────────────────── 리포트 ────────────────────────
def test_generate_report_empty(eng):
    r = eng.generate_workflow_report("SYSTEM", NOW, commit=True)
    assert r.workflow_count == 0
    assert r.is_binding is False
    assert r.requires_human_approval is True


def test_report_counts(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    eng.track_dependency(wf, t["b"], t["a"], NOW, commit=True)
    eng.plan_workflow(wf, now=NOW, commit=True)
    eng.start_workflow(wf, now=NOW, commit=True)
    eng.request_review(wf, "MID", "", NOW, commit=True)
    r = eng.generate_workflow_report("SYSTEM", NOW, commit=True)
    assert r.workflow_count == 1
    assert r.running_workflow_count == 1
    assert r.task_count == 2
    assert r.dependency_count == 1
    assert r.pending_review_count == 1


def test_report_state_distribution(eng):
    for n in ("a", "b"):
        eng.create_workflow(n, "d", NOW, commit=True)
    eng.plan_workflow(M.workflow_id("a"), now=NOW, commit=True)
    r = eng.generate_workflow_report("SYSTEM", NOW, commit=True)
    assert r.state_distribution.get(M.W_PLANNED) == 1
    assert r.state_distribution.get(M.W_CREATED) == 1


def test_report_disclaimer_mentions_no_auto_exec(eng):
    r = eng.generate_workflow_report("SYSTEM", NOW, commit=True)
    assert "AUTONOMOUS EXECUTION" in r.disclaimer


def test_report_deterministic(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    r1 = eng.generate_workflow_report("SYSTEM", NOW, commit=False)
    r2 = eng.generate_workflow_report("SYSTEM", NOW, commit=False)
    assert r1.to_dict() == r2.to_dict()


# ──────────────────────── 해시체인·검증 ────────────────────────
def test_verify_chain_clean(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    eng.track_dependency(wf, t["b"], t["a"], NOW, commit=True)
    eng.plan_workflow(wf, now=NOW, commit=True)
    eng.request_review(wf, "S", "", NOW, commit=True)
    eng.record_metadata(wf, "k", "v", NOW, commit=True)
    eng.generate_workflow_report("SYSTEM", NOW, commit=True)
    res = verify_chain()
    assert res["ok"]
    assert res["n"] > 0


def test_verify_empty_ok(eng):
    assert verify_chain()["ok"]


def test_hash_chain_links(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    eng.create_workflow("beta", "d", NOW, commit=True)
    recs = ledger.read_workflow_events()
    assert recs[0]["previous_hash"] == M.GENESIS
    assert recs[1]["previous_hash"] == recs[0]["record_hash"]


def test_tamper_detected(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("wf_workflows.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["name"] = "TAMPERED"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    res = verify_chain()
    assert not res["ok"]


def test_broken_chain_detected(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    eng.create_workflow("beta", "d", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("wf_workflows.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeefdeadbeef"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_duplicate_workflow_detected(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("wf_workflows.jsonl"))
    line = p.read_text().splitlines()[0]
    with p.open("a") as f:
        f.write(line + "\n")
    assert not duplicate_integrity()["ok"]


def test_bad_initial_workflow_state_detected(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("wf_workflows.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["to_state"] = M.W_RUNNING
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not workflow_lifecycle_integrity()["ok"]


def test_bad_initial_task_state_detected(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.add_task(wf, "collect", now=NOW, commit=True)
    p = pathlib.Path(ledger.state_path("wf_tasks.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["to_state"] = M.T_RUNNING
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not task_lifecycle_integrity()["ok"]


def test_auto_granted_approval_detected(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.request_review(wf, "S", "", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("wf_approvals.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["is_granted"] = True
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not approval_integrity()["ok"]


def test_dependency_integrity_ok(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    eng.track_dependency(wf, t["b"], t["a"], NOW, commit=True)
    assert dependency_integrity()["ok"]


def test_lineage_integrity_ok(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.add_task(wf, "collect", now=NOW, commit=True)
    assert lineage_integrity()["ok"]


def test_task_artifact_parent_is_workflow(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    wf = M.workflow_id("alpha")
    eng.add_task(wf, "collect", now=NOW, commit=True)
    arts = ledger.read_artifacts()
    tsk = M.task_id(wf, "collect")
    task_art = next(a for a in arts if a["ref_id"] == tsk)
    assert task_art["parent_artifact"] == M.artifact_id(M.ART_WORKFLOW, wf)


# ──────────────────────── 재현 ────────────────────────
def test_replay_deterministic(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    eng.track_dependency(wf, t["b"], t["a"], NOW, commit=True)
    r = replay(eng, NOW)
    assert r["deterministic"]
    assert r["workflow_count"] == 1
    assert r["task_count"] == 2


def test_summary_counts(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    eng.track_dependency(wf, t["b"], t["a"], NOW, commit=True)
    eng.plan_workflow(wf, now=NOW, commit=True)
    eng.request_review(wf, "S", "", NOW, commit=True)
    eng.record_metadata(wf, "k", "v", NOW, commit=True)
    eng.generate_workflow_report("SYSTEM", NOW, commit=True)
    s = eng.summary(NOW)
    assert s.workflow_count == 1
    assert s.task_count == 2
    assert s.dependency_count == 1
    assert s.approval_count == 1
    assert s.metadata_count == 1
    assert s.report_count == 1


def test_workflows_in_state(eng):
    for n in ("a", "b", "c"):
        eng.create_workflow(n, "d", NOW, commit=True)
    eng.plan_workflow(M.workflow_id("a"), now=NOW, commit=True)
    assert eng.workflows_in_state(M.W_PLANNED) == [M.workflow_id("a")]
    assert len(eng.workflows_in_state(M.W_CREATED)) == 2


# ──────────────────────── ID 접두사 ────────────────────────
@pytest.mark.parametrize("fn,args,prefix", [
    (M.workflow_id, ("x",), "WFW:"),
    (M.workflow_event_id, ("x", "CREATED", 0), "WFE:"),
    (M.task_id, ("wf", "t"), "WFT:"),
    (M.task_event_id, ("t", "PENDING", 0), "WFS:"),
    (M.dependency_id, ("wf", "a", "b"), "WFD:"),
    (M.approval_id, ("wf", "S", 0), "WFP:"),
    (M.metadata_id, ("wf", "k"), "WFM:"),
    (M.report_id, ("SYSTEM", NOW), "WFR:"),
    (M.artifact_id, ("WORKFLOW", "ref"), "WFA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_ids_deterministic():
    assert M.workflow_id("alpha") == M.workflow_id("alpha")
    assert M.task_id("wf", "t") == M.task_id("wf", "t")
    assert M.workflow_id("alpha") != M.workflow_id("beta")


# ──────────────────────── 안전(금지 동사/import/모델유출) ────────────────────────
@pytest.mark.parametrize("verb", [
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "AUTO_EXECUTE",
    "AUTO_RUN", "SELF_EXECUTE", "AUTO_APPROVE",
])
def test_forbidden_verbs(verb):
    assert M.is_forbidden_verb(verb)


def test_forbidden_verb_case_insensitive():
    assert M.is_forbidden_verb("execute")
    assert M.is_forbidden_verb(" Deploy ")


def test_not_forbidden_verbs():
    for v in ("analyze", "record", "simulate", "recommend", "advance", "plan"):
        assert not M.is_forbidden_verb(v)


_SRC_FILES = [str(SRC / f) for f in ("engine.py", "ledger.py", "models.py", "verify.py",
                                     "__main__.py", "__init__.py")]
_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_trading", "jarvis.portfolio_execution",
    "jarvis.live_portfolio", "jarvis.portfolio", "jarvis.order", "jarvis.deployment", "jarvis.live",
)


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_dangerous_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order", "activate_live",
           "auto_execute", "auto_run", "self_execute", "auto_approve", "grant", "grant_approval")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name
        if isinstance(node, ast.FunctionDef):
            assert not node.name.startswith(("delete_", "overwrite_", "drop_", "truncate", "purge_"))


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_engine_no_execution_methods(eng):
    for m in ("execute", "trade", "deploy", "allocate", "approve", "place_order", "activate_live"):
        assert not hasattr(eng, m)


# ──────────────────────── READ ONLY 소스 ────────────────────────
def test_source_layers_defined():
    assert "model_management" in ledger.SOURCE_LAYERS
    assert "experiment_tracking" in ledger.SOURCE_LAYERS
    assert "data_infrastructure" in ledger.SOURCE_LAYERS


def test_source_count_absent(eng):
    assert ledger.source_count("model_management") == 0
    assert ledger.source_present("model_management") is False


def test_all_source_counts(eng):
    counts = ledger.all_source_counts()
    assert set(counts) == set(ledger.SOURCE_LAYERS)
    assert all(v == 0 for v in counts.values())


def test_source_count_unknown_layer(eng):
    assert ledger.source_count("nonexistent") == 0


# ──────────────────────── 원장 접두사·격리 ────────────────────────
def test_all_ledger_files_wf_prefix():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("wf_")


def test_seven_ledgers():
    assert len(ledger.ALL_LEDGERS) == 7


def test_no_stray_state_files(eng):
    eng.create_workflow("alpha", "d", NOW, commit=True)
    written = {pathlib.Path(ledger.state_path(f)).name for f, _ in ledger.ALL_LEDGERS
               if pathlib.Path(ledger.state_path(f)).exists()}
    assert all(w.startswith("wf_") for w in written)


# ──────────────────────── CLI ────────────────────────
def _run_cli(argv, tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir(exist_ok=True)
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    from jarvis.workflow_automation import __main__ as cli
    return cli.main(argv)


def test_cli_workflow(tmp_path, monkeypatch, capsys):
    rc = _run_cli(["workflow", "--name", "alpha", "--commit"], tmp_path, monkeypatch)
    assert rc == 0
    assert "WFW:" in capsys.readouterr().out


def test_cli_advance(tmp_path, monkeypatch, capsys):
    _run_cli(["workflow", "--name", "alpha", "--commit"], tmp_path, monkeypatch)
    wf = M.workflow_id("alpha")
    rc = _run_cli(["advance", "--workflow", wf, "--to", "PLANNED", "--commit"], tmp_path, monkeypatch)
    assert rc == 0
    assert "PLANNED" in capsys.readouterr().out


def test_cli_task_and_depend(tmp_path, monkeypatch, capsys):
    _run_cli(["workflow", "--name", "alpha", "--commit"], tmp_path, monkeypatch)
    wf = M.workflow_id("alpha")
    _run_cli(["task", "--workflow", wf, "--name", "a", "--commit"], tmp_path, monkeypatch)
    _run_cli(["task", "--workflow", wf, "--name", "b", "--commit"], tmp_path, monkeypatch)
    ta, tb = M.task_id(wf, "a"), M.task_id(wf, "b")
    rc = _run_cli(["depend", "--workflow", wf, "--from-task", tb, "--to-task", ta, "--commit"],
                  tmp_path, monkeypatch)
    assert rc == 0
    assert "WFD:" in capsys.readouterr().out


def test_cli_review(tmp_path, monkeypatch, capsys):
    _run_cli(["workflow", "--name", "alpha", "--commit"], tmp_path, monkeypatch)
    wf = M.workflow_id("alpha")
    rc = _run_cli(["review", "--workflow", wf, "--stage", "PRE", "--commit"], tmp_path, monkeypatch)
    assert rc == 0
    out = capsys.readouterr().out
    assert "PENDING_HUMAN_REVIEW" in out


def test_cli_order(tmp_path, monkeypatch, capsys):
    _run_cli(["workflow", "--name", "alpha", "--commit"], tmp_path, monkeypatch)
    wf = M.workflow_id("alpha")
    _run_cli(["task", "--workflow", wf, "--name", "a", "--commit"], tmp_path, monkeypatch)
    rc = _run_cli(["order", "--workflow", wf], tmp_path, monkeypatch)
    assert rc == 0
    assert "recommended_order" in capsys.readouterr().out


def test_cli_report(tmp_path, monkeypatch, capsys):
    rc = _run_cli(["report", "--scope", "SYSTEM"], tmp_path, monkeypatch)
    assert rc == 0
    assert "is_binding" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _run_cli(["workflow", "--name", "alpha", "--commit"], tmp_path, monkeypatch)
    rc = _run_cli(["verify"], tmp_path, monkeypatch)
    assert rc == 0
    assert '"ok": true' in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    rc = _run_cli(["summary"], tmp_path, monkeypatch)
    assert rc == 0
    assert "workflow_count" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _run_cli(["workflow", "--name", "alpha", "--commit"], tmp_path, monkeypatch)
    rc = _run_cli(["replay"], tmp_path, monkeypatch)
    assert rc == 0
    assert "deterministic" in capsys.readouterr().out


def test_cli_metadata(tmp_path, monkeypatch, capsys):
    _run_cli(["workflow", "--name", "alpha", "--commit"], tmp_path, monkeypatch)
    wf = M.workflow_id("alpha")
    rc = _run_cli(["metadata", "--workflow", wf, "--key", "owner", "--value", "team", "--commit"],
                  tmp_path, monkeypatch)
    assert rc == 0
    assert "owner" in capsys.readouterr().out


def test_cli_task_adv(tmp_path, monkeypatch, capsys):
    _run_cli(["workflow", "--name", "alpha", "--commit"], tmp_path, monkeypatch)
    wf = M.workflow_id("alpha")
    _run_cli(["task", "--workflow", wf, "--name", "a", "--commit"], tmp_path, monkeypatch)
    tsk = M.task_id(wf, "a")
    rc = _run_cli(["task-adv", "--task", tsk, "--to", "READY", "--commit"], tmp_path, monkeypatch)
    assert rc == 0
    assert "READY" in capsys.readouterr().out


# ──────────────────────── 레코드 to_dict ────────────────────────
def test_records_to_dict_roundtrip(eng):
    wf, t = _wf_with_tasks(eng, ["a", "b"])
    d = eng.track_dependency(wf, t["b"], t["a"], NOW, commit=True)
    assert d.to_dict()["dependency_id"] == d.dependency_id
    r = eng.generate_workflow_report("SYSTEM", NOW, commit=False)
    assert r.to_dict()["is_binding"] is False


def test_content_hash_excludes_meta():
    rec = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    h1 = M.content_hash(rec)
    rec2 = {"a": 1, "previous_hash": "DIFFERENT", "record_hash": "OTHER"}
    assert h1 == M.content_hash(rec2)


def test_clamp01():
    assert M.clamp01(1.5) == 1.0
    assert M.clamp01(-0.2) == 0.0
    assert M.clamp01("bad") == 0.0
    assert M.clamp01(0.5) == 0.5


# ──────────────────────── 엔드투엔드 ────────────────────────
def test_end_to_end(eng):
    # 워크플로 생성 → 태스크 3개 → 의존성 사슬 → 계획/실행 → 검토요청 → 리포트
    eng.create_workflow("research-pipeline", "월간 연구 파이프라인", NOW, commit=True)
    wf = M.workflow_id("research-pipeline")
    for n, k in (("ingest", "DATA_PREP"), ("experiment", "EXPERIMENT"), ("report", "REPORTING")):
        eng.add_task(wf, n, k, NOW, commit=True)
    ti, te, tr = (M.task_id(wf, "ingest"), M.task_id(wf, "experiment"), M.task_id(wf, "report"))
    eng.track_dependency(wf, te, ti, NOW, commit=True)   # experiment depends on ingest
    eng.track_dependency(wf, tr, te, NOW, commit=True)   # report depends on experiment
    eng.plan_workflow(wf, now=NOW, commit=True)
    eng.start_workflow(wf, now=NOW, commit=True)
    eng.advance_task(ti, M.T_READY, now=NOW, commit=True)
    eng.advance_task(ti, M.T_RUNNING, now=NOW, commit=True)
    eng.advance_task(ti, M.T_COMPLETED, now=NOW, commit=True)
    eng.request_review(wf, "PRE_COMPLETION", "완료 전 사람 검토", NOW, commit=True)
    order = eng.task_execution_order(wf)
    assert order == [ti, te, tr]
    eng.complete_workflow(wf, now=NOW, commit=True)
    r = eng.generate_workflow_report("SYSTEM", NOW, commit=True)
    assert r.workflow_count == 1
    assert r.completed_workflow_count == 1
    assert r.task_count == 3
    assert r.dependency_count == 2
    assert r.pending_review_count == 1
    assert r.requires_human_approval is True
    res = verify_chain()
    assert res["ok"]
    assert res["workflow_lifecycle"]["ok"]
    assert res["task_lifecycle"]["ok"]
    assert res["dependency"]["ok"]
    assert res["approval"]["ok"]


def test_end_to_end_two_workflows_isolated(eng):
    eng.create_workflow("wf1", "d", NOW, commit=True)
    eng.create_workflow("wf2", "d", NOW, commit=True)
    w1, w2 = M.workflow_id("wf1"), M.workflow_id("wf2")
    eng.add_task(w1, "x", now=NOW, commit=True)
    eng.add_task(w2, "y", now=NOW, commit=True)
    assert ledger.task_ids_for(w1) == [M.task_id(w1, "x")]
    assert ledger.task_ids_for(w2) == [M.task_id(w2, "y")]
    assert verify_chain()["ok"]
