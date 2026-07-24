"""P12.9 Autonomous Research Manager 테스트. **계획·추적·모니터링 전용.**

계획 생애주기(CREATED→PLANNED→RUNNING→COMPLETED→REVIEWED→ARCHIVED)·작업(불변)·의존(dangling/순환 거부)·위상
정렬·진행 추적(→RUNNING)·상태 리포트(is_binding=False)·verify(체인/변조/중복/생애주기/의존/참조/계보)·replay·CLI·
보안(금지import·금지동사·삭제 API 없음·불변·MANAGE≠EXECUTION·rmgr_ 격리·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_manager import ledger
from jarvis.research_manager import models as M
from jarvis.research_manager.engine import AutonomousResearchManagerEngine
from jarvis.research_manager.models import (
    ALLOWED_TRANSITIONS,
    FORBIDDEN_VERBS,
    GENESIS,
    P_ARCHIVED,
    P_COMPLETED,
    P_CREATED,
    P_PLANNED,
    P_REVIEWED,
    P_RUNNING,
    PLAN_STATES,
    TASK_STATES,
    CircularDependencyError,
    DanglingDependencyError,
    IllegalPlanTransition,
    ImmutablePlanError,
    ImmutableTaskError,
    UnknownPlanError,
    UnknownTaskError,
    can_transition,
    content_hash,
    detect_cycle,
    is_forbidden_verb,
    topological_order,
)
from jarvis.research_manager.verify import (
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
    monkeypatch.setattr("jarvis.research_manager.ledger.state_path", sp)
    return sp


def _eng():
    return AutonomousResearchManagerEngine()


def _plan(e, name="plan1", objective="obj", now=T[0]):
    return e.create_research_plan(name, objective, now, commit=True).plan_id


def _task(e, plan, name="task1", now=T[1]):
    return e.create_task(plan, name, "desc", "owner", now, commit=True).task_id


def _running(e, name="plan1"):
    pid = _plan(e, name)
    tid = _task(e, pid)
    e.track_progress(tid, 10, "IN_PROGRESS", "n", T[2], commit=True)
    return pid, tid


# ═══════════════ 계획 생성 ═══════════════
def test_create_plan_returns_created(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_research_plan("p", "o", T[0], commit=True)
    assert ev.to_state == P_CREATED
    assert ev.from_state == GENESIS


def test_create_plan_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().create_research_plan("p", "o", T[0], commit=True).plan_id.startswith("RMG:")


def test_plan_event_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().create_research_plan("p", "o", T[0], commit=True).plan_event_id.startswith("RMD:")


def test_create_plan_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e)
    assert len(ledger.read_plan_events()) == 1


def test_create_plan_no_commit_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_research_plan("p", "o", T[0], commit=False)
    assert ledger.read_plan_events() == []


def test_create_plan_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().create_research_plan("p", "o", T[0], commit=False).plan_id
    b = _eng().create_research_plan("p", "o", T[5], commit=False).plan_id
    assert a == b


def test_create_plan_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_research_plan("p", "o", T[0], commit=True).plan_id
    b = e.create_research_plan("p", "o", T[1], commit=True).plan_id
    assert a == b
    assert len(ledger.plan_events(a)) == 1


def test_create_plan_immutable_objective(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_research_plan("p", "o", T[0], commit=True)
    with pytest.raises(ImmutablePlanError):
        e.create_research_plan("p", "different", T[1], commit=True)


def test_create_plan_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e)
    assert len(ledger.read_artifacts()) == 1


def test_create_plan_state_is_created(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    assert e.current_state(pid) == P_CREATED


# ═══════════════ 작업 생성 ═══════════════
def test_create_task_returns_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    t = e.create_task(pid, "t", "d", "o", T[1], commit=True)
    assert t.task_id.startswith("RMT:")
    assert t.plan_id == pid


def test_create_task_transitions_to_planned(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    _task(e, pid)
    assert e.current_state(pid) == P_PLANNED


def test_create_second_task_no_extra_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    _task(e, pid, "t1")
    _task(e, pid, "t2")
    assert e.current_state(pid) == P_PLANNED
    # genesis + one PLANNED transition
    assert len(ledger.plan_events(pid)) == 2


def test_create_task_unknown_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPlanError):
        _eng().create_task("RMG:nope", "t", "d", "o", T[1], commit=True)


def test_create_task_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    e.create_task(pid, "t", "desc1", "o", T[1], commit=True)
    with pytest.raises(ImmutableTaskError):
        e.create_task(pid, "t", "desc2", "o", T[2], commit=True)


def test_create_task_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = e.create_task(pid, "t", "d", "o", T[1], commit=True).task_id
    b = e.create_task(pid, "t", "d", "o", T[2], commit=True).task_id
    assert a == b
    assert len(ledger.read_tasks()) == 1


def test_create_task_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = e.create_task(pid, "t", "d", "o", T[1], commit=False).task_id
    b = e.create_task(pid, "t", "d", "o", T[3], commit=False).task_id
    assert a == b


def test_create_task_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    e.create_task(pid, "t", "d", "o", T[1], commit=False)
    assert ledger.read_tasks() == []


def test_create_task_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    _task(e, pid)
    # plan artifact + task artifact
    assert len(ledger.read_artifacts()) == 2


def test_list_tasks(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    t1 = _task(e, pid, "a")
    t2 = _task(e, pid, "b")
    assert sorted([t1, t2]) == e.list_tasks(pid)


# ═══════════════ 의존 ═══════════════
def test_resolve_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    b = _task(e, pid, "b")
    d = e.resolve_dependency(a, b, T[3], commit=True)
    assert d.dependency_id.startswith("RMP:")
    assert d.task_id == a
    assert d.depends_on == b


def test_dependency_dangling_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    with pytest.raises(DanglingDependencyError):
        e.resolve_dependency(a, "RMT:nope", T[3], commit=True)


def test_dependency_unknown_task_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    with pytest.raises(UnknownTaskError):
        e.resolve_dependency("RMT:nope", a, T[3], commit=True)


def test_dependency_self_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    with pytest.raises(CircularDependencyError):
        e.resolve_dependency(a, a, T[3], commit=True)


def test_dependency_circular_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    b = _task(e, pid, "b")
    e.resolve_dependency(a, b, T[3], commit=True)
    with pytest.raises(CircularDependencyError):
        e.resolve_dependency(b, a, T[4], commit=True)


def test_dependency_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    b = _task(e, pid, "b")
    x = e.resolve_dependency(a, b, T[3], commit=True).dependency_id
    y = e.resolve_dependency(a, b, T[4], commit=True).dependency_id
    assert x == y
    assert len(ledger.read_dependencies()) == 1


def test_dependency_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    b = _task(e, pid, "b")
    e.resolve_dependency(a, b, T[3], commit=False)
    assert ledger.read_dependencies() == []


# ═══════════════ 위상 정렬 ═══════════════
def test_task_order_linear(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    b = _task(e, pid, "b")
    c = _task(e, pid, "c")
    e.resolve_dependency(b, a, T[3], commit=True)  # b depends on a
    e.resolve_dependency(c, b, T[4], commit=True)  # c depends on b
    order = e.task_order(pid)
    assert order.index(a) < order.index(b) < order.index(c)


def test_task_order_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    _task(e, pid, "a")
    _task(e, pid, "b")
    assert e.task_order(pid) == e.task_order(pid)


def test_task_order_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    assert e.task_order(pid) == []


# ═══════════════ 진행 추적 ═══════════════
def test_track_progress_transitions_running(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    tid = _task(e, pid)
    e.track_progress(tid, 10, "IN_PROGRESS", "n", T[2], commit=True)
    assert e.current_state(pid) == P_RUNNING


def test_track_progress_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    tid = _task(e, pid)
    p = e.track_progress(tid, 50, "IN_PROGRESS", "n", T[2], commit=True)
    assert p.progress_id.startswith("RMV:")
    assert p.percent == 50
    assert p.task_id == tid


def test_track_progress_unknown_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownTaskError):
        _eng().track_progress("RMT:nope", 10, "IN_PROGRESS", "n", T[2], commit=True)


def test_track_progress_multiple_seq(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    tid = _task(e, pid)
    p1 = e.track_progress(tid, 10, "IN_PROGRESS", "a", T[2], commit=True)
    p2 = e.track_progress(tid, 20, "IN_PROGRESS", "b", T[3], commit=True)
    assert p1.progress_id != p2.progress_id
    assert len(ledger.task_progress(tid)) == 2


def test_track_progress_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    tid = _task(e, pid)
    e.track_progress(tid, 10, "IN_PROGRESS", "n", T[2], commit=False)
    assert ledger.read_progress() == []


def test_track_progress_already_running_no_extra_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    tid = _task(e, pid)
    e.track_progress(tid, 10, "IN_PROGRESS", "n", T[2], commit=True)
    n = len(ledger.plan_events(pid))
    e.track_progress(tid, 20, "IN_PROGRESS", "n", T[3], commit=True)
    assert len(ledger.plan_events(pid)) == n


# ═══════════════ 생애주기 전이 ═══════════════
def test_complete_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    ev = e.complete_plan(pid, T[5], commit=True)
    assert ev.to_state == P_COMPLETED


def test_review_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    e.complete_plan(pid, T[5], commit=True)
    ev = e.review_plan(pid, T[6], commit=True)
    assert ev.to_state == P_REVIEWED


def test_archive_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    e.complete_plan(pid, T[5], commit=True)
    e.review_plan(pid, T[6], commit=True)
    ev = e.archive_plan(pid, T[7], commit=True)
    assert ev.to_state == P_ARCHIVED


def test_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    e.complete_plan(pid, T[5], commit=True)
    e.review_plan(pid, T[6], commit=True)
    e.archive_plan(pid, T[7], commit=True)
    assert e.current_state(pid) == P_ARCHIVED


def test_complete_before_running_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    with pytest.raises(IllegalPlanTransition):
        e.complete_plan(pid, T[5], commit=True)


def test_review_before_complete_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    with pytest.raises(IllegalPlanTransition):
        e.review_plan(pid, T[6], commit=True)


def test_archive_before_review_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    e.complete_plan(pid, T[5], commit=True)
    with pytest.raises(IllegalPlanTransition):
        e.archive_plan(pid, T[7], commit=True)


def test_archived_is_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    e.complete_plan(pid, T[5], commit=True)
    e.review_plan(pid, T[6], commit=True)
    e.archive_plan(pid, T[7], commit=True)
    with pytest.raises(IllegalPlanTransition):
        e.complete_plan(pid, T[8], commit=True)


def test_transition_unknown_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPlanError):
        _eng().complete_plan("RMG:nope", T[5], commit=True)


def test_reviewed_can_rerun(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    e.complete_plan(pid, T[5], commit=True)
    e.review_plan(pid, T[6], commit=True)
    ev = e._transition(pid, P_RUNNING, "rerun", T[7], commit=True)
    assert ev.to_state == P_RUNNING


# ═══════════════ 상태 리포트 ═══════════════
def test_status_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    r = e.generate_status_report(pid, "PLAN", T[8], commit=True)
    assert r.is_binding is False


def test_status_report_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    r = e.generate_status_report(pid, "PLAN", T[8], commit=True)
    assert r.report_id.startswith("RMN:")


def test_status_report_task_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    _task(e, pid, "a")
    _task(e, pid, "b")
    r = e.generate_status_report(pid, "PLAN", T[8], commit=True)
    assert r.task_count == 2


def test_status_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    r = e.generate_status_report(pid, "PLAN", T[8], commit=True)
    assert "EXECUTION" in r.disclaimer


def test_status_report_done_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    tid = _task(e, pid)
    e.track_progress(tid, 100, "DONE", "done", T[2], commit=True)
    r = e.generate_status_report(pid, "PLAN", T[8], commit=True)
    assert r.done_count == 1


def test_status_report_unknown_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPlanError):
        _eng().generate_status_report("RMG:nope", "PLAN", T[8], commit=True)


def test_status_report_dependency_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    b = _task(e, pid, "b")
    e.resolve_dependency(a, b, T[3], commit=True)
    r = e.generate_status_report(pid, "PLAN", T[8], commit=True)
    assert r.dependency_count == 1


# ═══════════════ 조회 ═══════════════
def test_list_plans(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e, "a")
    _plan(e, "b")
    assert len(e.list_plans()) == 2


def test_plans_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e, "a")
    pid = _plan(e, "b")
    _task(e, pid)
    assert e.plans_in_state(P_CREATED) == [_eng().create_research_plan("a", "obj").plan_id]
    assert pid in e.plans_in_state(P_PLANNED)


def test_plan_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e, "myplan", "myobj")
    m = e.plan_meta(pid)
    assert m["name"] == "myplan"
    assert m["objective"] == "myobj"
    assert m["state"] == P_CREATED


def test_plan_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPlanError):
        _eng().plan_meta("RMG:nope")


def test_current_state_none(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_state("RMG:nope") is None


# ═══════════════ Summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, tid = _running(e)
    s = e.summary(T[9])
    assert s.plan_event_count >= 2
    assert s.task_count == 1
    assert s.progress_count == 1


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().summary(T[0])
    assert s.plan_event_count == 0
    assert s.artifact_count == 0


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    e.complete_plan(pid, T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_integrity_engine(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e)
    p = sp("rmgr_plans.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e, "a")
    _plan(e, "b")
    p = sp("rmgr_plans.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e)
    p = sp("rmgr_plans.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running(e)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e, "a")
    _plan(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_dependency_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    b = _task(e, pid, "b")
    e.resolve_dependency(a, b, T[3], commit=True)
    assert dependency_integrity()["ok"] is True


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running(e)
    assert reference_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running(e)
    assert lineage_integrity()["ok"] is True


def test_dependency_integrity_detects_dangling(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    b = _task(e, pid, "b")
    e.resolve_dependency(a, b, T[3], commit=True)
    p = sp("rmgr_dependencies.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["depends_on"] = "RMT:ghost"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert dependency_integrity()["ok"] is False


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _running(e)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ can_transition matrix ═══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (P_CREATED, P_PLANNED, True),
    (P_CREATED, P_RUNNING, False),
    (P_CREATED, P_COMPLETED, False),
    (P_PLANNED, P_RUNNING, True),
    (P_PLANNED, P_COMPLETED, False),
    (P_RUNNING, P_COMPLETED, True),
    (P_RUNNING, P_RUNNING, True),
    (P_RUNNING, P_REVIEWED, False),
    (P_COMPLETED, P_REVIEWED, True),
    (P_COMPLETED, P_ARCHIVED, False),
    (P_REVIEWED, P_ARCHIVED, True),
    (P_REVIEWED, P_RUNNING, True),
    (P_ARCHIVED, P_PLANNED, False),
    (P_ARCHIVED, P_RUNNING, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert can_transition(frm, to) is ok


@pytest.mark.parametrize("state", PLAN_STATES)
def test_plan_states_present(state):
    assert state in PLAN_STATES


@pytest.mark.parametrize("state", PLAN_STATES)
def test_transition_map_has_state(state):
    assert state in ALLOWED_TRANSITIONS


def test_archived_has_no_transitions():
    assert ALLOWED_TRANSITIONS[P_ARCHIVED] == set()


@pytest.mark.parametrize("st", TASK_STATES)
def test_task_states(st):
    assert st in TASK_STATES


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb_detected(verb):
    assert is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["PLAN", "TRACK", "REVIEW", "REPORT", "OBSERVE", "RECORD"])
def test_allowed_verb_not_forbidden(verb):
    assert is_forbidden_verb(verb) is False


@pytest.mark.parametrize("verb", ["start_trading", "Deploy_Model", "  execute  ", "TRADE"])
def test_forbidden_verb_normalized(verb):
    assert is_forbidden_verb(verb) is True


def test_forbidden_verb_empty():
    assert is_forbidden_verb("") is False
    assert is_forbidden_verb(None) is False


@pytest.mark.parametrize("v", ["START_TRADING", "RUN_ORDER", "PLACE_ORDER", "DEPLOY_MODEL",
                                "ALLOCATE_CAPITAL", "PROMOTE_MODEL", "CHANGE_PERMISSION"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


# ═══════════════ detect_cycle / topological_order ═══════════════
def test_detect_cycle_simple():
    assert detect_cycle([("a", "b"), ("b", "a")]) != []


def test_detect_cycle_none():
    assert detect_cycle([("a", "b"), ("b", "c")]) == []


def test_detect_cycle_self():
    assert detect_cycle([("a", "a")]) != []


def test_topological_order_valid():
    order = topological_order(["a", "b", "c"], [("b", "a"), ("c", "b")])
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_order_cycle_empty():
    assert topological_order(["a", "b"], [("a", "b"), ("b", "a")]) == []


def test_topological_order_deterministic():
    a = topological_order(["a", "b", "c"], [])
    b = topological_order(["a", "b", "c"], [])
    assert a == b == ["a", "b", "c"]


# ═══════════════ ID 결정성/구별 ═══════════════
def test_ids_distinct():
    assert M.plan_id("x") != M.task_id("x", "y")
    assert M.plan_event_id("p", "S", 0) != M.progress_id("t", 0)


@pytest.mark.parametrize("fn,args,prefix", [
    (M.plan_id, ("n",), "RMG:"),
    (M.plan_event_id, ("p", "S", 0), "RMD:"),
    (M.task_id, ("p", "n"), "RMT:"),
    (M.dependency_id, ("a", "b"), "RMP:"),
    (M.progress_id, ("t", 0), "RMV:"),
    (M.report_id, ("p", "s", "t"), "RMN:"),
    (M.artifact_id, ("PLAN", "r"), "RMF:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "DIFF", "record_hash": "DIFF"}
    assert content_hash(r1) == content_hash(r2)


def test_content_hash_changes_on_content():
    assert content_hash({"a": 1}) != content_hash({"a": 2})


# ═══════════════ 소스 READ ONLY ═══════════════
def test_source_ledgers_configured():
    assert "autonomous_research_pipeline" in ledger.SOURCE_LEDGERS
    assert "research_experience_memory" in ledger.SOURCE_LEDGERS
    assert "research_learning" in ledger.SOURCE_LEDGERS


def test_source_ref_missing_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("nope", "x") is False


def test_source_ref_missing_file(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("autonomous_research_pipeline", "x") is False


# ═══════════════ 보안: 소스 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.capital_allocation", "jarvis.live_trading", "jarvis.risk_controller",
    "jarvis.portfolio_execution",
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
    bad = ("execute_trade", "place_order", "run_order", "start_trading", "deploy_model",
           "allocate_capital", "promote_model", "change_permission", "submit_order",
           "send_order", "route_order", "liquidate", "rebalance")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_delete_or_update_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def update_", "def remove_", "def drop_", "def overwrite_"):
        assert bad not in src, bad


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    # 오직 append("a") 모드만
    assert '"a"' in src
    assert '"w"' not in src
    assert '"r+"' not in src


@pytest.mark.parametrize("path", _SRC)
def test_all_source_files_have_disclaimer_or_manager(path):
    # 계층 문서화: 파일 내 관리자/연구 문구 존재(모듈 docstring)
    src = open(path).read()
    assert "연구" in src or "Research" in src or "research" in src


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rmgr_")


def test_source_files_prefix_isolation():
    # 본 계층 소스는 자기 원장 접두사(rmgr_)만 기록 대상으로 삼는다
    src = open(os.path.join(_PKG, "ledger.py")).read()
    for own, _ in ledger.ALL_LEDGERS:
        assert own in src


# ═══════════════ CLI ═══════════════
def test_cli_plan(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    assert main(["plan", "--name", "p", "--objective", "o", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["plan"]["to_state"] == P_CREATED


def test_cli_task_and_progress(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    main(["plan", "--name", "p", "--commit"])
    pid = json.loads(capsys.readouterr().out)["plan"]["plan_id"]
    main(["task", "--plan", pid, "--name", "t", "--commit"])
    tid = json.loads(capsys.readouterr().out)["task"]["task_id"]
    assert main(["progress", "--task", tid, "--percent", "20", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["progress"]["percent"] == 20


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    assert main(["verify"]) == 0


def test_cli_plans(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    main(["plan", "--name", "p", "--commit"])
    capsys.readouterr()
    assert main(["plans"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["plans"]) == 1


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    assert main(["summary"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["plan_event_count"] == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    main(["plan", "--name", "p", "--commit"])
    pid = json.loads(capsys.readouterr().out)["plan"]["plan_id"]
    assert main(["report", "--plan", pid, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_full_lifecycle(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    main(["plan", "--name", "p", "--commit"])
    pid = json.loads(capsys.readouterr().out)["plan"]["plan_id"]
    main(["task", "--plan", pid, "--name", "t", "--commit"])
    tid = json.loads(capsys.readouterr().out)["task"]["task_id"]
    main(["progress", "--task", tid, "--percent", "50", "--commit"])
    capsys.readouterr()
    assert main(["complete", "--plan", pid, "--commit"]) == 0
    capsys.readouterr()
    assert main(["review", "--plan", pid, "--commit"]) == 0
    capsys.readouterr()
    assert main(["archive", "--plan", pid, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == P_ARCHIVED


def test_cli_depend_and_order(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    main(["plan", "--name", "p", "--commit"])
    pid = json.loads(capsys.readouterr().out)["plan"]["plan_id"]
    main(["task", "--plan", pid, "--name", "a", "--commit"])
    a = json.loads(capsys.readouterr().out)["task"]["task_id"]
    main(["task", "--plan", pid, "--name", "b", "--commit"])
    b = json.loads(capsys.readouterr().out)["task"]["task_id"]
    main(["depend", "--task", b, "--on", a, "--commit"])
    capsys.readouterr()
    assert main(["order", "--plan", pid]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["task_order"].index(a) < out["task_order"].index(b)


def test_cli_tasks(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_manager.__main__ import main
    main(["plan", "--name", "p", "--commit"])
    pid = json.loads(capsys.readouterr().out)["plan"]["plan_id"]
    main(["task", "--plan", pid, "--name", "t", "--commit"])
    capsys.readouterr()
    assert main(["tasks", "--plan", pid]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["tasks"]) == 1


# ═══════════════ 격리: 실제 _state 오염 없음 ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_research_plan("p", "o", T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "rmgr_plans.jsonl"))


def test_records_immutable_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.create_research_plan("p", "o", T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"  # frozen dataclass


# ═══════════════ 추가 엣지 케이스 ═══════════════
def test_two_plans_independent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p1 = _plan(e, "a")
    p2 = _plan(e, "b")
    _task(e, p1, "t")
    assert e.current_state(p1) == P_PLANNED
    assert e.current_state(p2) == P_CREATED


def test_task_order_only_plan_tasks(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p1 = _plan(e, "a")
    p2 = _plan(e, "b")
    t1 = _task(e, p1, "t1")
    _task(e, p2, "t2")
    assert e.task_order(p1) == [t1]


def test_progress_records_plan_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    tid = _task(e, pid)
    p = e.track_progress(tid, 10, "IN_PROGRESS", "n", T[2], commit=True)
    assert p.plan_id == pid


def test_status_report_progress_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    tid = _task(e, pid)
    e.track_progress(tid, 10, "IN_PROGRESS", "a", T[2], commit=True)
    e.track_progress(tid, 20, "IN_PROGRESS", "b", T[3], commit=True)
    r = e.generate_status_report(pid, "PLAN", T[8], commit=True)
    assert r.progress_count == 2


def test_status_report_plan_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    r = e.generate_status_report(pid, "PLAN", T[8], commit=True)
    assert r.plan_state == P_RUNNING


def test_verify_reports_ledger(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    e.generate_status_report(pid, "PLAN", T[8], commit=True)
    res = verify_chain()
    assert res["ledgers"]["rmgr_reports.jsonl"]["ok"] is True


def test_all_ledgers_verify_after_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    a = _task(e, pid, "a")
    b = _task(e, pid, "b")
    e.resolve_dependency(b, a, T[3], commit=True)
    e.track_progress(a, 100, "DONE", "x", T[4], commit=True)
    e.track_progress(b, 100, "DONE", "y", T[5], commit=True)
    e.complete_plan(pid, T[6], commit=True)
    e.review_plan(pid, T[7], commit=True)
    e.archive_plan(pid, T[8], commit=True)
    e.generate_status_report(pid, "PLAN", T[9], commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] > 0


def test_artifact_lineage_task_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _plan(e)
    _task(e, pid)
    arts = ledger.read_artifacts()
    task_arts = [a for a in arts if a.get("artifact_type") == "TASK"]
    assert task_arts and task_arts[0].get("parent_artifact")


def test_report_idempotent_same_time(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    r1 = e.generate_status_report(pid, "PLAN", T[8], commit=True).report_id
    r2 = e.generate_status_report(pid, "PLAN", T[8], commit=True).report_id
    assert r1 == r2
    assert len(ledger.read_reports()) == 1


def test_plan_events_ordered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid, _ = _running(e)
    e.complete_plan(pid, T[5], commit=True)
    evs = ledger.plan_events(pid)
    states = [x["to_state"] for x in evs]
    assert states == [P_CREATED, P_PLANNED, P_RUNNING, P_COMPLETED]


# ═══════════════ End-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = e.create_research_plan("momentum-study", "test momentum", T[0], commit=True).plan_id
    a = e.create_task(pid, "collect-data", "d", "alice", T[1], commit=True).task_id
    b = e.create_task(pid, "run-backtest", "d", "bob", T[2], commit=True).task_id
    c = e.create_task(pid, "analyze", "d", "carol", T[3], commit=True).task_id
    e.resolve_dependency(b, a, T[4], commit=True)
    e.resolve_dependency(c, b, T[5], commit=True)
    order = e.task_order(pid)
    assert order.index(a) < order.index(b) < order.index(c)
    e.track_progress(a, 100, "DONE", "done", T[6], commit=True)
    assert e.current_state(pid) == P_RUNNING
    e.track_progress(b, 100, "DONE", "done", T[7], commit=True)
    e.track_progress(c, 100, "DONE", "done", T[8], commit=True)
    e.complete_plan(pid, T[9], commit=True)
    e.review_plan(pid, T[10], commit=True)
    r = e.generate_status_report(pid, "PLAN", T[11], commit=True)
    assert r.done_count == 3
    assert r.is_binding is False
    e.archive_plan(pid, T[12], commit=True)
    assert e.current_state(pid) == P_ARCHIVED
    assert verify_chain()["ok"] is True
    assert replay(e, T[13])["deterministic"] is True
