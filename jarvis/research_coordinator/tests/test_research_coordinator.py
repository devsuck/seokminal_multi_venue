"""P11.7 Autonomous Research Coordinator 테스트. **다중 연구 에이전트 조율 — 조율·기록 전용.**

코디네이터 등록·플랜 생애주기(CREATED→…→ARCHIVED)·태스크 배정/재분배(완료 불변)·진행 갱신·의존성 그래프(순환
거부·자기의존 거부)·스케줄러(위상·웨이브)·정체 탐지·워크로드 균형·에스컬레이션·완료 리포트·아티팩트 계보·
verify(체인/변조/중복/플랜·태스크 생애주기/DAG/계보)·replay·CLI·보안(금지import·실행/거래/배포/상위수정 없음·삭제
API 없음·불변·COORDINATION≠EXECUTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_coordinator import ledger
from jarvis.research_coordinator import models as M
from jarvis.research_coordinator.engine import ResearchCoordinatorEngine
from jarvis.research_coordinator.models import (
    P_ARCHIVED,
    P_ASSIGNING,
    P_BLOCKED,
    P_COMPLETED,
    P_CREATED,
    P_PLANNING,
    P_REBALANCING,
    P_RUNNING,
    T_ASSIGNED,
    T_BLOCKED,
    T_COMPLETED,
    T_IN_PROGRESS,
    CompletedTaskError,
    DependencyCycleError,
    IllegalPlanTransition,
    IllegalTaskTransition,
    ImmutableCoordinatorError,
    InvalidSeverity,
    PlanClosedError,
    SelfDependencyError,
    UnknownCoordinatorError,
    UnknownPlanError,
    UnknownTaskError,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(40)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_coordinator.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchCoordinatorEngine()


def _coord(e, name="research_coord", now=T[0]):
    return e.register_coordinator(name, "orchestrate agents", now, commit=True).coordinator_id


def _plan(e, coord=None, name="momentum_study", now=T[0]):
    if coord is None:
        coord = _coord(e, now=now)
    return e.create_plan(coord, name, "study momentum", now, commit=True).plan_id


def _running_plan(e):
    """RUNNING 플랜."""
    coord = _coord(e)
    p = e.create_plan(coord, "study", "obj", T[0], commit=True).plan_id
    e.start_planning(p, T[1], commit=True)
    e.start_assigning(p, T[2], commit=True)
    e.start_running(p, T[3], commit=True)
    return coord, p


# ══════════════ register_coordinator ══════════════
def test_coordinator_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().register_coordinator("c1", "m", T[0], commit=True)
    assert c.coordinator_id.startswith("COO:")


def test_coordinator_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_coordinator("c", "m", T[0], commit=False)
    b = _eng().register_coordinator("c", "m2", T[1], commit=False)
    assert a.coordinator_id == b.coordinator_id


def test_coordinator_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _coord(e)
    _coord(e, now=T[1])
    assert len(ledger.read_coordinators()) == 1


def test_coordinator_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _coord(e)
    assert any(a["artifact_type"] == "COORDINATOR" for a in ledger.read_artifacts())


# ══════════════ create_plan / lifecycle ══════════════
def test_plan_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    assert e.current_state(p) == P_CREATED


def test_plan_unknown_coordinator(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownCoordinatorError):
        _eng().create_plan("COO:ghost", "n", "", T[0], commit=True)


def test_plan_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    assert e.current_state(p) == P_RUNNING
    e.mark_blocked(p, T[4], commit=True)
    assert e.current_state(p) == P_BLOCKED
    e.resume_running(p, T[5], commit=True)
    e.start_rebalancing(p, T[6], commit=True)
    assert e.current_state(p) == P_REBALANCING
    e.resume_running(p, T[7], commit=True)
    e.complete_plan(p, T[8], commit=True)
    assert e.current_state(p) == P_COMPLETED
    e.archive_plan(p, T[9], commit=True)
    assert e.current_state(p) == P_ARCHIVED


def test_plan_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    with pytest.raises(IllegalPlanTransition):
        e.start_running(p, T[1], commit=True)  # CREATED->RUNNING 불가


def test_plan_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.complete_plan(p, T[4], commit=True)
    e.archive_plan(p, T[5], commit=True)
    with pytest.raises(IllegalPlanTransition):
        e.resume_running(p, T[6], commit=True)


def test_plan_idempotent_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _coord(e)
    e.create_plan(c, "n", "o", T[0], commit=True)
    e.create_plan(c, "n", "o", T[1], commit=True)
    assert len(ledger.plan_ids()) == 1


def test_plan_transition_emits_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    e.start_planning(p, T[1], commit=True)
    assert any(ev["kind"] == "PLAN_TRANSITION" for ev in ledger.read_events())


def test_eight_plan_states():
    assert len(M.PLAN_STATES) == 8


# ══════════════ assign_task ══════════════
def test_assign_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    a = e.assign_task(p, "collect_data", "data_agent", T[4], commit=True)
    assert a.assignment_event_id.startswith("CAE:")
    assert a.owner == "data_agent"
    assert a.state == T_ASSIGNED


def test_assign_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    assert any(a["artifact_type"] == "ASSIGNMENT" for a in ledger.read_artifacts())


def test_assign_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.assign_task(p, "t", "b", T[5], commit=True)  # 이미 존재 → idempotent
    assert e.task_owner(p, "t") == "a"


def test_assign_on_closed_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.complete_plan(p, T[4], commit=True)
    with pytest.raises(PlanClosedError):
        e.assign_task(p, "t", "a", T[5], commit=True)


def test_assign_emits_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    assert any(ev["kind"] == "TASK_ASSIGNED" for ev in ledger.read_events())


# ══════════════ reassign_task (ownership) ══════════════
def test_reassign_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "agent_a", T[4], commit=True)
    r = e.reassign_task(p, "t", "agent_b", T[5], commit=True)
    assert r.is_reassignment is True
    assert r.owner == "agent_b"
    assert e.task_owner(p, "t") == "agent_b"


def test_reassign_unknown_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    with pytest.raises(UnknownTaskError):
        e.reassign_task(p, "ghost", "b", T[4], commit=True)


def test_reassign_completed_task_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.update_progress(p, "t", 100, T_COMPLETED, "", T[5], commit=True)
    with pytest.raises(CompletedTaskError):
        e.reassign_task(p, "t", "b", T[6], commit=True)


def test_reassign_emits_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.reassign_task(p, "t", "b", T[5], commit=True)
    assert any(ev["kind"] == "TASK_REASSIGNED" for ev in ledger.read_events())


# ══════════════ update_progress ══════════════
def test_update_progress(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    pr = e.update_progress(p, "t", 50, T_IN_PROGRESS, "halfway", T[5], commit=True)
    assert pr.progress_id.startswith("COG:")
    assert pr.percent == 50
    assert e.task_state(p, "t") == T_IN_PROGRESS


def test_progress_to_completed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.update_progress(p, "t", 100, T_COMPLETED, "", T[5], commit=True)
    assert e.task_state(p, "t") == T_COMPLETED


def test_progress_completed_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.update_progress(p, "t", 100, T_COMPLETED, "", T[5], commit=True)
    with pytest.raises(CompletedTaskError):
        e.update_progress(p, "t", 50, T_IN_PROGRESS, "", T[6], commit=True)


def test_progress_illegal_task_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.update_progress(p, "t", 100, T_COMPLETED, "", T[5], commit=True)
    # COMPLETED 는 종료 → CompletedTaskError 먼저 (별도 케이스). BLOCKED 전이 자체 테스트:
    e2 = e
    e2.assign_task(p, "t2", "a", T[6], commit=True)
    e2.update_progress(p, "t2", 10, T_BLOCKED, "", T[7], commit=True)
    assert e2.task_state(p, "t2") == T_BLOCKED


def test_progress_percent_clamped(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    pr = e.update_progress(p, "t", 150, T_IN_PROGRESS, "", T[5], commit=True)
    assert pr.percent == 100


def test_progress_unknown_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    with pytest.raises(UnknownTaskError):
        e.update_progress(p, "ghost", 10, T_IN_PROGRESS, "", T[4], commit=True)


# ══════════════ dependency graph ══════════════
def _tasks(e, p, names, t0=4):
    for i, n in enumerate(names):
        e.assign_task(p, n, "agent", T[t0 + i], commit=True)


def test_add_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    d = e.add_dependency(p, "a", "b", T[10], commit=True)
    assert d.dependency_id.startswith("COD:")


def test_dependency_self_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a"])
    with pytest.raises(SelfDependencyError):
        e.add_dependency(p, "a", "a", T[10], commit=True)


def test_dependency_cycle_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b", "c"])
    e.add_dependency(p, "a", "b", T[10], commit=True)
    e.add_dependency(p, "b", "c", T[11], commit=True)
    with pytest.raises(DependencyCycleError):
        e.add_dependency(p, "c", "a", T[12], commit=True)
    assert len(ledger.plan_dependencies(p)) == 2


def test_dependency_unknown_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a"])
    with pytest.raises(UnknownTaskError):
        e.add_dependency(p, "a", "ghost", T[10], commit=True)


def test_dependency_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    e.add_dependency(p, "a", "b", T[10], commit=True)
    e.add_dependency(p, "a", "b", T[11], commit=True)
    assert len(ledger.plan_dependencies(p)) == 1


# ══════════════ scheduler ══════════════
def test_build_schedule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b", "c"])
    e.add_dependency(p, "a", "b", T[10], commit=True)
    e.add_dependency(p, "b", "c", T[11], commit=True)
    s = e.build_schedule(p, T[12], commit=True)
    ta, tb, tc = (M.task_id(p, x) for x in ("a", "b", "c"))
    assert s.order.index(ta) < s.order.index(tb) < s.order.index(tc)
    assert s.task_count == 3


def test_schedule_waves(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b", "c"])
    e.add_dependency(p, "a", "c", T[10], commit=True)
    e.add_dependency(p, "b", "c", T[11], commit=True)
    s = e.build_schedule(p, T[12], commit=True)
    ta, tb, tc = (M.task_id(p, x) for x in ("a", "b", "c"))
    assert s.waves[0] == sorted([ta, tb])
    assert s.waves[1] == [tc]


def test_schedule_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    e.add_dependency(p, "a", "b", T[10], commit=True)
    s1 = e.build_schedule(p, T[11], commit=False)
    s2 = e.build_schedule(p, T[12], commit=False)
    assert s1.order == s2.order


# ══════════════ detect_blocker (stalled detection) ══════════════
def test_detect_blocker_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.update_progress(p, "t", 10, T_BLOCKED, "stuck", T[5], commit=True)
    res = e.detect_blocker(p, T[6], commit=True)
    assert M.task_id(p, "t") in res["blocked"]
    assert res["stalled_count"] == 1


def test_detect_blocker_waiting_on_dep(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    e.add_dependency(p, "a", "b", T[10], commit=True)  # b 는 a 완료 대기
    res = e.detect_blocker(p, T[11], commit=True)
    assert M.task_id(p, "b") in res["waiting"]


def test_detect_blocker_none_when_clear(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.update_progress(p, "t", 50, T_IN_PROGRESS, "", T[5], commit=True)
    res = e.detect_blocker(p, T[6], commit=True)
    assert res["stalled_count"] == 0


def test_detect_blocker_emits_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.update_progress(p, "t", 10, T_BLOCKED, "", T[5], commit=True)
    e.detect_blocker(p, T[6], commit=True)
    assert any(ev["kind"] == "BLOCKER_DETECTED" for ev in ledger.read_events())


def test_detect_blocker_dep_satisfied(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    e.add_dependency(p, "a", "b", T[10], commit=True)
    e.update_progress(p, "a", 100, T_COMPLETED, "", T[11], commit=True)
    res = e.detect_blocker(p, T[12], commit=True)
    assert M.task_id(p, "b") not in res["waiting"]


# ══════════════ rebalance_workload ══════════════
def test_rebalance_workload(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t1", "agent_a", T[4], commit=True)
    e.assign_task(p, "t2", "agent_a", T[5], commit=True)
    e.assign_task(p, "t3", "agent_a", T[6], commit=True)
    e.assign_task(p, "t4", "agent_b", T[7], commit=True)
    w = e.rebalance_workload(p, T[10], commit=True)
    assert w.workload_id.startswith("COW:")
    assert w.distribution["agent_a"] == 3
    assert w.distribution["agent_b"] == 1
    assert w.imbalance == 2
    assert len(w.suggested_moves) == 1  # (3-1)//2


def test_rebalance_balanced(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t1", "a", T[4], commit=True)
    e.assign_task(p, "t2", "b", T[5], commit=True)
    w = e.rebalance_workload(p, T[10], commit=True)
    assert w.imbalance == 0
    assert w.suggested_moves == []


def test_rebalance_excludes_completed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t1", "a", T[4], commit=True)
    e.update_progress(p, "t1", 100, T_COMPLETED, "", T[5], commit=True)
    w = e.rebalance_workload(p, T[10], commit=True)
    assert "a" not in w.distribution


def test_rebalance_emits_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t1", "a", T[4], commit=True)
    e.rebalance_workload(p, T[10], commit=True)
    assert any(ev["kind"] == "WORKLOAD_REBALANCED" for ev in ledger.read_events())


def test_workload_imbalance_pure():
    assert M.workload_imbalance({"a": 3, "b": 1}) == 2
    assert M.workload_imbalance({}) == 0


def test_suggest_moves_pure():
    assert M.suggest_moves({"a": 4, "b": 0}) == [{"from": "a", "to": "b"},
                                                 {"from": "a", "to": "b"}]
    assert M.suggest_moves({"a": 1}) == []


# ══════════════ escalate_issue ══════════════
def test_escalate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    x = e.escalate_issue(p, "t", "no progress 3 days", "CRITICAL", T[5], commit=True)
    assert x.escalation_id.startswith("COX:")
    assert x.severity == "CRITICAL"
    assert x.resolved is False


def test_escalate_invalid_severity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    with pytest.raises(InvalidSeverity):
        e.escalate_issue(p, "", "x", "HUGE", T[4], commit=True)


@pytest.mark.parametrize("sev", list(M.SEVERITIES))
def test_escalate_all_severities(tmp_path, monkeypatch, sev):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    x = e.escalate_issue(p, "", f"r_{sev}", sev, T[4], commit=True)
    assert x.severity == sev


def test_escalate_emits_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.escalate_issue(p, "", "r", "WARNING", T[4], commit=True)
    assert any(ev["kind"] == "ISSUE_ESCALATED" for ev in ledger.read_events())


# ══════════════ complete_plan / generate_report ══════════════
def test_complete_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.complete_plan(p, T[4], commit=True)
    assert e.current_state(p) == P_COMPLETED


def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t1", "a", T[4], commit=True)
    e.update_progress(p, "t1", 100, T_COMPLETED, "", T[5], commit=True)
    e.assign_task(p, "t2", "b", T[6], commit=True)
    r = e.generate_report(p, "PLAN", T[10], commit=True)
    assert r.report_id.startswith("COR:")
    assert r.task_count == 2
    assert r.completed_count == 1
    assert r.is_binding is False


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    a = e.generate_report(p, "PLAN", T[4], commit=False)
    b = e.generate_report(p, "PLAN", T[4], commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    r = e.generate_report(p, "PLAN", T[4], commit=True)
    assert "COORDINATION ≠ EXECUTION" in r.disclaimer


def test_report_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.generate_report(p, "PLAN", T[4], commit=True)
    assert any(a["artifact_type"] == "REPORT" for a in ledger.read_artifacts())


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_coordinator.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_full_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_coordinator.verify import verify_chain
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    e.add_dependency(p, "a", "b", T[10], commit=True)
    e.update_progress(p, "a", 100, T_COMPLETED, "", T[11], commit=True)
    e.reassign_task(p, "b", "agent_c", T[12], commit=True)
    e.build_schedule(p, T[13], commit=True)
    e.detect_blocker(p, T[14], commit=True)
    e.rebalance_workload(p, T[15], commit=True)
    e.escalate_issue(p, "b", "slow", "WARNING", T[16], commit=True)
    e.complete_plan(p, T[17], commit=True)
    e.generate_report(p, "PLAN", T[18], commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["plan_lifecycle"]["ok"]
    assert res["task_lifecycle"]["ok"]
    assert res["dag"]["ok"]
    assert res["lineage"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _coord(e)
    fp = sp("rco_coordinators.jsonl")
    rows = [json.loads(x) for x in open(fp)]
    rows[0]["name"] = "TAMPERED"
    with open(fp, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_coordinator.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_verify_dag_integrity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_coordinator.verify import dag_integrity
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    e.add_dependency(p, "a", "b", T[10], commit=True)
    assert dag_integrity()["ok"] is True


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_coordinator.verify import replay
    e = _eng()
    _running_plan(e)
    assert replay(e, T[5])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.escalate_issue(p, "t", "r", "INFO", T[5], commit=True)
    s = e.summary(T[10])
    assert s.coordinator_count == 1
    assert s.assignment_event_count == 1
    assert s.escalation_count == 1


# ══════════════ 보안 / 불변식 (no execution / no upstream mutation) ══════════════
def test_no_forbidden_imports():
    import ast
    forbidden_prefixes = ("execution", "broker", "portfolio", "risk", "permission", "deployment",
                          "live", "order", "capital_allocation", "live_trading", "risk_controller",
                          "portfolio_execution")
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "ledger.py", "models.py", "verify.py", "__main__.py", "__init__.py"):
        tree = ast.parse(open(os.path.join(base, fn)).read())
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                mods = [n.module or ""]
            for m in mods:
                if not m.startswith("jarvis."):
                    continue
                sub = m[len("jarvis."):]
                for fb in forbidden_prefixes:
                    assert not (sub == fb or sub.startswith(fb)), (fn, m)


def test_engine_no_execution_methods():
    e = ResearchCoordinatorEngine()
    for bad in ("trade", "execute", "deploy", "broker", "allocate", "modify_permission",
                "change_config", "promote_strategy", "promote_model", "modify_portfolio",
                "approve", "activate"):
        assert not hasattr(e, bad), bad


def test_no_execution_verbs_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def trade", "def execute", "def deploy", "def broker", "def allocate",
                    "def promote_strategy", "def promote_model", "def modify_portfolio",
                    "def modify_permission", "def change_config"):
            assert bad not in src, (fn, bad)


def test_forbidden_verbs_defined():
    for v in ("TRADE", "EXECUTE", "DEPLOY", "BROKER", "ALLOCATION", "PROMOTE_STRATEGY",
              "PROMOTE_MODEL"):
        assert M.is_forbidden_verb(v) is True
    assert M.is_forbidden_verb("ASSIGN") is False


def test_no_delete_or_update_api():
    import inspect
    src = inspect.getsource(ledger)
    for bad in ("def delete", "def update", "def remove", "def overwrite", "def edit_"):
        assert bad not in src, bad


def test_ledger_only_appends():
    import inspect
    src = inspect.getsource(ledger)
    assert '"a"' in src
    assert 'open(p, "w"' not in src


def test_disclaimer_marks_no_execution():
    from jarvis.research_coordinator.engine import _DISCLAIMER
    assert "COORDINATION ≠ EXECUTION" in _DISCLAIMER
    assert "REBALANCE ≠ DEPLOYMENT" in _DISCLAIMER


def test_records_frozen():
    r = M.AssignmentEventRecord(assignment_event_id="CAE:x", task_id="COK:t", plan_id="COP:p",
                                task_name="n", owner="o", state="ASSIGNED", is_reassignment=False,
                                note="", occurred_at=T[0])
    with pytest.raises(Exception):
        r.owner = "z"  # type: ignore


def test_only_rco_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    e.add_dependency(p, "a", "b", T[10], commit=True)
    e.build_schedule(p, T[11], commit=True)
    e.rebalance_workload(p, T[12], commit=True)
    e.escalate_issue(p, "a", "r", "INFO", T[13], commit=True)
    e.complete_plan(p, T[14], commit=True)
    e.generate_report(p, "PLAN", T[15], commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("rco_"), fn


def test_all_reports_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.generate_report(p, "PLAN", T[4], commit=True)
    for r in ledger.read_reports():
        assert r["is_binding"] is False


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.coordinator_id("n")[:4], M.plan_id("c", "n")[:4], M.plan_event_id("p", "s", 0)[:4],
           M.task_id("p", "t")[:4], M.assignment_event_id("t", 0)[:4],
           M.dependency_id("p", "u", "d")[:4], M.progress_id("t", 0)[:4],
           M.schedule_id("p", 0)[:4], M.workload_id("p", 0)[:4], M.event_id("p", "k", 0)[:4],
           M.escalation_id("p", "t", 0)[:4], M.report_id("p", "s", T[0])[:4],
           M.artifact_id("t", "r")[:4]}
    assert len(ids) == 13


def test_eleven_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 11
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 11
    assert all(f.startswith("rco_") for f in fns)


def test_four_task_states():
    assert len(M.TASK_STATES) == 4


def test_eight_event_kinds():
    assert len(M.EVENT_KINDS) == 8


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b")]) == []
    cyc = M.detect_cycle([("a", "b"), ("b", "a")])
    assert cyc and cyc[0] == cyc[-1]


def test_topological_sort_pure():
    assert M.topological_sort(["a", "b"], [("a", "b")]) == ["a", "b"]
    assert M.topological_sort(["a", "b"], [("a", "b"), ("b", "a")]) is None


def test_list_plans_and_tasks(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "collect", "a", T[4], commit=True)
    assert p in e.list_plans(coord)
    assert "collect" in e.list_tasks(p)


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_coordinator.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_coordinator_plan_assign(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["coordinator", "--name", "c1", "--commit"], capsys)
    assert rc == 0
    cid = json.loads(out)["coordinator"]["coordinator_id"]
    rc2, out2 = _run(["plan", "--coordinator", cid, "--name", "pl", "--commit"], capsys)
    pid = json.loads(out2)["plan"]["plan_id"]
    _run(["advance", "--plan", pid, "--to", "PLANNING", "--commit"], capsys)
    _run(["advance", "--plan", pid, "--to", "ASSIGNING", "--commit"], capsys)
    _run(["advance", "--plan", pid, "--to", "RUNNING", "--commit"], capsys)
    rc3, out3 = _run(["assign", "--plan", pid, "--task", "t1", "--owner", "a", "--commit"], capsys)
    assert rc3 == 0
    assert json.loads(out3)["assignment"]["owner"] == "a"


def test_cli_depend_schedule(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    rc, out = _run(["depend", "--plan", p, "--up", "a", "--down", "b", "--commit"], capsys)
    assert rc == 0
    rc2, out2 = _run(["schedule", "--plan", p, "--commit"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["schedule"]["task_count"] == 2


def test_cli_progress_reassign(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    rc, out = _run(["progress", "--plan", p, "--task", "t", "--percent", "50",
                    "--state", "IN_PROGRESS", "--commit"], capsys)
    assert rc == 0
    rc2, out2 = _run(["reassign", "--plan", p, "--task", "t", "--owner", "b", "--commit"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["assignment"]["owner"] == "b"


def test_cli_blockers_rebalance_escalate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    rc, out = _run(["blockers", "--plan", p], capsys)
    assert rc == 0
    rc2, out2 = _run(["rebalance", "--plan", p, "--commit"], capsys)
    assert rc2 == 0
    rc3, out3 = _run(["escalate", "--plan", p, "--reason", "slow", "--severity", "WARNING",
                      "--commit"], capsys)
    assert rc3 == 0
    assert json.loads(out3)["escalation"]["severity"] == "WARNING"


def test_cli_report_and_lists(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    rc, out = _run(["report", "--plan", p, "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["report"]["is_binding"] is False
    rc2, out2 = _run(["tasks", "--plan", p], capsys)
    assert "t" in json.loads(out2)["tasks"]


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _running_plan(_eng())
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "coordinator_count" in json.loads(out)


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (P_CREATED, P_PLANNING, True), (P_PLANNING, P_ASSIGNING, True), (P_ASSIGNING, P_RUNNING, True),
    (P_RUNNING, P_BLOCKED, True), (P_RUNNING, P_REBALANCING, True), (P_RUNNING, P_COMPLETED, True),
    (P_BLOCKED, P_RUNNING, True), (P_REBALANCING, P_RUNNING, True), (P_COMPLETED, P_ARCHIVED, True),
    (P_CREATED, P_RUNNING, False), (P_ARCHIVED, P_RUNNING, False), (P_PLANNING, P_COMPLETED, False),
])
def test_plan_transition_matrix(frm, to, ok):
    assert M.can_transition_plan(frm, to) is ok


@pytest.mark.parametrize("frm,to,ok", [
    (T_ASSIGNED, T_IN_PROGRESS, True), (T_ASSIGNED, T_BLOCKED, True), (T_ASSIGNED, T_COMPLETED, True),
    (T_IN_PROGRESS, T_COMPLETED, True), (T_BLOCKED, T_IN_PROGRESS, True),
    (T_COMPLETED, T_IN_PROGRESS, False), (T_IN_PROGRESS, T_ASSIGNED, False),
])
def test_task_transition_matrix(frm, to, ok):
    assert M.can_transition_task(frm, to) is ok


def test_plan_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _coord(e)
    e.create_plan(c, "n", "o", T[0], commit=False)
    assert ledger.read_plan_events() == []


def test_assign_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=False)
    assert ledger.read_assignments() == []


def test_dependency_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    e.add_dependency(p, "a", "b", T[10], commit=False)
    assert ledger.read_dependencies() == []


def test_reassign_on_closed_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.complete_plan(p, T[5], commit=True)
    with pytest.raises(PlanClosedError):
        e.reassign_task(p, "t", "b", T[6], commit=True)


def test_multiple_plans_isolated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _coord(e)
    p1 = e.create_plan(c, "p1", "o", T[0], commit=True).plan_id
    p2 = e.create_plan(c, "p2", "o", T[0], commit=True).plan_id
    for p in (p1, p2):
        e.start_planning(p, T[1], commit=True)
        e.start_assigning(p, T[2], commit=True)
        e.start_running(p, T[3], commit=True)
    e.assign_task(p1, "t", "a", T[4], commit=True)
    assert len(ledger.plan_task_ids(p1)) == 1
    assert len(ledger.plan_task_ids(p2)) == 0


def test_schedule_no_deps(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    s = e.build_schedule(p, T[10], commit=True)
    assert s.waves == [sorted([M.task_id(p, "a"), M.task_id(p, "b")])]


def test_task_owner_empty_for_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    assert e.task_owner(p, "ghost") == ""


def test_report_dag_flag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    _tasks(e, p, ["a", "b"])
    e.add_dependency(p, "a", "b", T[10], commit=True)
    r = e.generate_report(p, "PLAN", T[11], commit=True)
    assert r.is_dag is True


def test_escalation_immutable_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.escalate_issue(p, "", "r1", "INFO", T[4], commit=True)
    e.escalate_issue(p, "", "r2", "WARNING", T[5], commit=True)
    assert len(ledger.plan_escalations(p)) == 2


def test_progress_records_accumulate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.assign_task(p, "t", "a", T[4], commit=True)
    e.update_progress(p, "t", 30, T_IN_PROGRESS, "", T[5], commit=True)
    e.update_progress(p, "t", 60, T_IN_PROGRESS, "", T[6], commit=True)
    assert len(ledger.task_progress(M.task_id(p, "t"))) == 2


def test_build_waves_pure():
    assert M.build_waves(["a", "b", "c"], [("a", "c"), ("b", "c")]) == [["a", "b"], ["c"]]
    assert M.build_waves(["a", "b"], [("a", "b"), ("b", "a")]) is None


def test_plan_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPlanError):
        _eng().plan_meta("COP:ghost")


def test_report_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord, p = _running_plan(e)
    e.generate_report(p, "PLAN", T[4], commit=False)
    assert ledger.read_reports() == []


def test_three_severities():
    assert set(M.SEVERITIES) == {"INFO", "WARNING", "CRITICAL"}


# ══════════════ 통합 시나리오 (end-to-end workflow) ══════════════
def test_end_to_end_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    coord = e.register_coordinator("alpha_coordinator", "orchestrate momentum research", T[0],
                                   commit=True).coordinator_id
    p = e.create_plan(coord, "momentum_v3_study", "validate momentum v3", T[0], commit=True).plan_id
    e.start_planning(p, T[1], commit=True)
    e.start_assigning(p, T[2], commit=True)
    e.start_running(p, T[3], commit=True)
    # 4 tasks, chained + parallel
    for i, (task, owner) in enumerate([("collect", "data_agent"), ("features", "data_agent"),
                                       ("backtest", "sim_agent"), ("review", "reviewer_agent")]):
        e.assign_task(p, task, owner, T[4 + i], commit=True)
    e.add_dependency(p, "collect", "features", T[10], commit=True)
    e.add_dependency(p, "features", "backtest", T[11], commit=True)
    e.add_dependency(p, "backtest", "review", T[12], commit=True)
    sched = e.build_schedule(p, T[13], commit=True)
    assert sched.task_count == 4
    # progress
    e.update_progress(p, "collect", 100, T_COMPLETED, "done", T[14], commit=True)
    e.update_progress(p, "features", 40, T_IN_PROGRESS, "", T[15], commit=True)
    # workload: data_agent has 2 (features assigned+in_progress, collect completed excluded)
    w = e.rebalance_workload(p, T[16], commit=True)
    assert w.distribution.get("data_agent", 0) >= 1
    # blocker: backtest waits on features
    bl = e.detect_blocker(p, T[17], commit=True)
    assert M.task_id(p, "backtest") in bl["waiting"]
    # reassign features to another agent (ownership rebalance)
    e.reassign_task(p, "features", "data_agent_2", T[18], commit=True)
    assert e.task_owner(p, "features") == "data_agent_2"
    # escalate
    e.escalate_issue(p, "features", "slow progress", "WARNING", T[19], commit=True)
    e.mark_blocked(p, T[20], commit=True)
    e.resume_running(p, T[21], commit=True)
    e.complete_plan(p, T[22], commit=True)
    e.archive_plan(p, T[23], commit=True)
    rep = e.generate_report(p, "PLAN", T[24], commit=True)
    assert rep.task_count == 4
    assert rep.completed_count == 1
    assert rep.is_dag is True
    assert rep.is_binding is False
    from jarvis.research_coordinator.verify import verify_chain
    v = verify_chain()
    assert v["ok"] is True
    assert v["plan_lifecycle"]["ok"] and v["task_lifecycle"]["ok"] and v["dag"]["ok"] and v["lineage"]["ok"]
