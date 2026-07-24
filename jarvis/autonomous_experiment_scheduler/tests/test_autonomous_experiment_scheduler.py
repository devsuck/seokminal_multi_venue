"""P12.2 Autonomous Experiment Scheduler 테스트. **스케줄·기록 전용.**

큐 생애주기(REQUESTED→…→ARCHIVED)·의존 그래프(순환/dangling 차단)·우선순위 로직(무단 변경 차단)·중복 요청 차단·
실행 계획(위상+우선순위 결정성)·정책·스냅샷/리포트(is_binding=False)·verify(체인/변조/중복/생애주기/의존/고아)·replay·
CLI·보안(금지import·실행 없음·삭제 API 없음·불변·SCHEDULE≠EXECUTION·append-only·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.autonomous_experiment_scheduler import ledger
from jarvis.autonomous_experiment_scheduler import models as M
from jarvis.autonomous_experiment_scheduler.engine import AutonomousExperimentSchedulerEngine
from jarvis.autonomous_experiment_scheduler.models import (
    Q_ARCHIVED,
    Q_COMPLETED,
    Q_PLANNED,
    Q_QUEUED,
    Q_READY,
    Q_REQUESTED,
    Q_SCHEDULED,
    SCHEDULE_STATES,
    CircularScheduleError,
    DanglingDependencyError,
    DuplicateRequestError,
    IllegalScheduleTransition,
    ImmutablePolicyError,
    ImmutableScheduleError,
    PriorityChangeError,
    UnknownRequestError,
    UnknownScheduleError,
)
from jarvis.autonomous_experiment_scheduler.verify import (
    dependency_integrity,
    duplicate_integrity,
    lifecycle_integrity,
    orphan_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]
_STATE_SEQ = [Q_QUEUED, Q_PLANNED, Q_READY, Q_SCHEDULED, Q_COMPLETED, Q_ARCHIVED]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.autonomous_experiment_scheduler.ledger.state_path", sp)
    return sp


def _eng():
    return AutonomousExperimentSchedulerEngine()


def _schedule(e, name="exp_queue", now=T[0]):
    return e.create_schedule(name, "schedule experiments", now, commit=True).schedule_id


def _request(e, sch=None, exp="EXP1", now=T[1]):
    if sch is None:
        sch = _schedule(e)
    return e.register_experiment_request(sch, exp, "", now, commit=True).request_id


def _advance_to(e, req, target, start_t=2):
    for i, st in enumerate(_STATE_SEQ):
        e.update_schedule_state(req, st, "", T[start_t + i], commit=True)
        if st == target:
            break
    return req


# ══════════════ Phase 0 / 접두사 / 소유 ══════════════
def test_prefix_all_ledgers_aes():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("aes_")


def test_seven_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 7


def test_source_ledgers_includes_p12_1():
    assert "autonomous_research_pipeline" in ledger.SOURCE_LEDGERS


def test_seven_lifecycle_states():
    assert len(SCHEDULE_STATES) == 7


# ══════════════ create_schedule ══════════════
def test_create_schedule_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_schedule("q", "m", T[0], commit=True)
    b = e.create_schedule("q", "m", T[1], commit=False)
    assert a.schedule_id == b.schedule_id
    assert a.schedule_id.startswith("ESG:")


def test_create_schedule_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_schedule("q", "m", T[0], commit=True)
    e.create_schedule("q", "m", T[1], commit=True)
    assert len(ledger.read_schedules()) == 1


def test_create_schedule_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_schedule("q", "m1", T[0], commit=True)
    with pytest.raises(ImmutableScheduleError):
        e.create_schedule("q", "m2", T[1], commit=True)


def test_create_schedule_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_schedule("q", "m", T[0], commit=False)
    assert ledger.read_schedules() == []


# ══════════════ register_experiment_request (queue lifecycle) ══════════════
def test_register_request_genesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    assert req.startswith("ESQ:")
    assert e.current_state(req) == Q_REQUESTED


def test_register_request_requires_schedule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownScheduleError):
        e.register_experiment_request("ESG:ghost", "EXP1", "", T[1], commit=True)


def test_register_request_duplicate_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    e.register_experiment_request(sch, "EXP1", "", T[1], commit=True)
    with pytest.raises(DuplicateRequestError):
        e.register_experiment_request(sch, "EXP1", "", T[2], commit=True)


def test_register_request_distinct_experiments(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    assert r1 != r2


# ══════════════ update_schedule_state (lifecycle) ══════════════
def test_advance_to_queued(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    e.update_schedule_state(req, Q_QUEUED, "", T[2], commit=True)
    assert e.current_state(req) == Q_QUEUED


def test_full_lifecycle_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    _advance_to(e, req, Q_ARCHIVED)
    assert e.current_state(req) == Q_ARCHIVED
    states = [ev["to_state"] for ev in ledger.request_events(req)]
    assert states == list(SCHEDULE_STATES)


def test_skip_transition_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    with pytest.raises(IllegalScheduleTransition):
        e.update_schedule_state(req, Q_SCHEDULED, "", T[2], commit=True)


def test_reverse_transition_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    _advance_to(e, req, Q_READY)
    with pytest.raises(IllegalScheduleTransition):
        e.update_schedule_state(req, Q_QUEUED, "", T[20], commit=True)


def test_unknown_request_advance(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownRequestError):
        e.update_schedule_state("ESQ:ghost", Q_QUEUED, "", T[2], commit=True)


@pytest.mark.parametrize("bad", [Q_PLANNED, Q_READY, Q_SCHEDULED, Q_COMPLETED, Q_ARCHIVED])
def test_various_skips_from_requested(tmp_path, monkeypatch, bad):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    with pytest.raises(IllegalScheduleTransition):
        e.update_schedule_state(req, bad, "", T[2], commit=True)


# ══════════════ assign_priority ══════════════
def test_assign_priority_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    p = e.assign_priority(req, 5, "high", T[2], commit=True)
    assert p.priority_id.startswith("ESR:")
    assert p.priority == 5


def test_assign_priority_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    e.assign_priority(req, 5, "", T[2], commit=True)
    e.assign_priority(req, 5, "", T[3], commit=True)
    assert len(ledger.read_priorities()) == 1


def test_assign_priority_unauthorized_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    e.assign_priority(req, 5, "", T[2], commit=True)
    with pytest.raises(PriorityChangeError):
        e.assign_priority(req, 9, "", T[3], commit=True)


def test_request_priority_default_zero(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    assert e.request_priority(req) == 0


# ══════════════ create_scheduling_policy ══════════════
def test_create_policy_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    p = e.create_scheduling_policy(sch, "fifo", "first-in-first-out", T[1], commit=True)
    assert p.policy_id.startswith("ESP:")


def test_create_policy_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    e.create_scheduling_policy(sch, "p", "r1", T[1], commit=True)
    with pytest.raises(ImmutablePolicyError):
        e.create_scheduling_policy(sch, "p", "r2", T[2], commit=True)


# ══════════════ resolve_dependencies (dependency graph) ══════════════
def test_resolve_dependency_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    deps = e.resolve_dependencies(r2, [r1], T[3], commit=True)
    assert len(deps) == 1
    assert r1 in e.request_dependencies(r2)


def test_resolve_dependency_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    with pytest.raises(DanglingDependencyError):
        e.resolve_dependencies(req, ["ESQ:ghost"], T[3], commit=True)


def test_resolve_dependency_self_circular(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    with pytest.raises(CircularScheduleError):
        e.resolve_dependencies(req, [req], T[3], commit=True)


def test_resolve_dependency_circular(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    e.resolve_dependencies(r2, [r1], T[3], commit=True)
    with pytest.raises(CircularScheduleError):
        e.resolve_dependencies(r1, [r2], T[4], commit=True)


def test_resolve_dependency_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    r3 = e.register_experiment_request(sch, "EXP3", "", T[3], commit=True).request_id
    e.resolve_dependencies(r2, [r1], T[4], commit=True)
    e.resolve_dependencies(r3, [r2], T[5], commit=True)
    assert len(ledger.read_dependencies()) == 2


# ══════════════ build_execution_plan (topological + priority) ══════════════
def test_build_plan_respects_dependencies(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    e.resolve_dependencies(r2, [r1], T[3], commit=True)
    e.update_schedule_state(r1, Q_QUEUED, "", T[4], commit=True)
    e.update_schedule_state(r2, Q_QUEUED, "", T[5], commit=True)
    plan = e.build_execution_plan(sch, "SCHEDULABLE", T[6], commit=True).plan
    assert plan.index(r1) < plan.index(r2)


def test_build_plan_priority_tiebreak(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    e.assign_priority(r1, 1, "", T[3], commit=True)
    e.assign_priority(r2, 9, "", T[4], commit=True)
    e.update_schedule_state(r1, Q_QUEUED, "", T[5], commit=True)
    e.update_schedule_state(r2, Q_QUEUED, "", T[6], commit=True)
    plan = e.build_execution_plan(sch, "SCHEDULABLE", T[7], commit=True).plan
    # 높은 우선순위(r2) 먼저
    assert plan.index(r2) < plan.index(r1)


def test_build_plan_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    e.update_schedule_state(r1, Q_QUEUED, "", T[2], commit=True)
    a = e.build_execution_plan(sch, "SCHEDULABLE", T[3], commit=False)
    b = e.build_execution_plan(sch, "SCHEDULABLE", T[3], commit=False)
    assert a.plan == b.plan
    assert a.snapshot_id == b.snapshot_id


def test_build_plan_excludes_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    _advance_to(e, r1, Q_COMPLETED, start_t=2)
    plan = e.build_execution_plan(sch, "SCHEDULABLE", T[20], commit=True).plan
    assert r1 not in plan  # COMPLETED 는 스케줄 가능 아님


def test_build_plan_only_requested_excluded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    # REQUESTED 는 SCHEDULABLE 아님
    plan = e.build_execution_plan(sch, "SCHEDULABLE", T[6], commit=True).plan
    assert r1 not in plan


# ══════════════ topological_order pure ══════════════
def test_topological_order_pure():
    order = M.topological_order(["a", "b", "c"], [("b", "a"), ("c", "b")], {})
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_order_priority():
    order = M.topological_order(["a", "b"], [], {"a": 1, "b": 5})
    assert order == ["b", "a"]


def test_topological_order_cycle_empty():
    assert M.topological_order(["a", "b"], [("a", "b"), ("b", "a")], {}) == []


# ══════════════ report / snapshot ══════════════
def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    _advance_to(e, r1, Q_COMPLETED, start_t=2)
    rep = e.generate_schedule_report(sch, "ALL", T[20], commit=True)
    assert rep.request_count == 1
    assert rep.completed_count == 1


def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    rep = e.generate_schedule_report(sch, "ALL", T[1], commit=True)
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    rep = e.generate_schedule_report(sch, "ALL", T[1], commit=True)
    assert "SCHEDULE ≠ EXECUTION" in rep.disclaimer


def test_report_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    e.register_experiment_request(sch, "EXP1", "", T[1], commit=True)
    rep = e.generate_schedule_report(sch, "ALL", T[2], commit=True)
    assert rep.state_distribution.get(Q_REQUESTED) == 1


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    e.assign_priority(r1, 5, "", T[3], commit=True)
    e.resolve_dependencies(r2, [r1], T[4], commit=True)
    _advance_to(e, r1, Q_SCHEDULED, start_t=5)
    e.build_execution_plan(sch, "SCHEDULABLE", T[15], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    p = ledger.state_path(ledger.SCHEDULES[0])
    recs = ledger.read_schedule_events()
    recs[0]["experiment_ref"] = "TAMPERED"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    e.update_schedule_state(req, Q_QUEUED, "", T[2], commit=True)
    p = ledger.state_path(ledger.SCHEDULES[0])
    recs = ledger.read_schedule_events()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.SCHEDULES[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _request(e)
    p = ledger.state_path(ledger.SCHEDULES[0])
    recs = ledger.read_schedule_events()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.SCHEDULES[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    _advance_to(e, req, Q_READY)
    assert lifecycle_integrity()["ok"] is True


def test_lifecycle_integrity_bad_initial(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng()
    p = ledger.state_path(ledger.SCHEDULES[0])
    bad = {"schedule_event_id": "ESV:bad", "request_id": "ESQ:bad", "schedule_id": "ESG:x",
           "from_state": M.GENESIS, "to_state": Q_QUEUED, "previous_hash": M.GENESIS}
    bad["record_hash"] = M.content_hash(bad)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps(bad, ensure_ascii=False) + "\n")
    assert lifecycle_integrity()["ok"] is False


def test_duplicate_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    p = ledger.state_path(ledger.SCHEDULES[0])
    g = [r for r in ledger.request_events(req) if r["from_state"] == M.GENESIS][0]
    with open(p, "a") as f:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
    assert duplicate_integrity()["ok"] is False


def test_dependency_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    e.resolve_dependencies(r2, [r1], T[3], commit=True)
    assert dependency_integrity()["ok"] is True


def test_dependency_integrity_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    e.resolve_dependencies(r2, [r1], T[3], commit=True)
    p = ledger.state_path(ledger.DEPENDENCIES[0])
    recs = ledger.read_dependencies()
    recs[0]["depends_on"] = "ESQ:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert dependency_integrity()["ok"] is False


def test_dependency_integrity_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP2", "", T[2], commit=True).request_id
    e.resolve_dependencies(r2, [r1], T[3], commit=True)
    # r1->r2 위조 주입으로 순환
    p = ledger.state_path(ledger.DEPENDENCIES[0])
    recs = ledger.read_dependencies()
    forged = dict(recs[0])
    forged["dependency_id"] = "ESD:forged00000"
    forged["request_id"] = r1
    forged["depends_on"] = r2
    forged["previous_hash"] = recs[0]["record_hash"]
    forged["record_hash"] = M.content_hash(forged)
    with open(p, "a") as f:
        f.write(json.dumps(forged, ensure_ascii=False, default=str) + "\n")
    assert dependency_integrity()["ok"] is False


def test_orphan_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _request(e)
    assert orphan_integrity()["ok"] is True


def test_orphan_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    e.assign_priority(req, 5, "", T[2], commit=True)
    p = ledger.state_path(ledger.PRIORITIES[0])
    recs = ledger.read_priorities()
    recs[0]["request_id"] = "ESQ:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert orphan_integrity()["ok"] is False


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _request(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    e.assign_priority(req, 5, "", T[2], commit=True)
    s = e.summary(T[9])
    assert s.schedule_count == 1
    assert s.priority_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _request(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _request(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_requests_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    assert req in e.requests_in_state(Q_REQUESTED)


def test_list_requests_by_schedule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    e.register_experiment_request(sch, "EXP1", "", T[1], commit=True)
    assert len(e.list_requests(sch)) == 1


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (Q_REQUESTED, Q_QUEUED, True),
    (Q_QUEUED, Q_PLANNED, True),
    (Q_PLANNED, Q_READY, True),
    (Q_READY, Q_SCHEDULED, True),
    (Q_SCHEDULED, Q_COMPLETED, True),
    (Q_COMPLETED, Q_ARCHIVED, True),
    (Q_REQUESTED, Q_SCHEDULED, False),
    (Q_READY, Q_QUEUED, False),
    (Q_ARCHIVED, Q_QUEUED, False),
    (Q_COMPLETED, Q_REQUESTED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "PROMOTE_LIVE",
                                  "APPROVE", "PLACE_ORDER", "EXECUTE_TRADE", "change_permission"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["SCHEDULE", "QUEUE", "PLAN", "PRIORITIZE", "RESOLVE", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.schedule_id("x") == M.schedule_id("x")
    assert M.request_id("s", "e") == M.request_id("s", "e")


def test_ids_prefixes_es_scheme():
    assert M.schedule_id("x").startswith("ESG:")
    assert M.request_id("s", "e").startswith("ESQ:")
    assert M.schedule_event_id("r", "s", 0).startswith("ESV:")
    assert M.policy_id("s", "n").startswith("ESP:")
    assert M.priority_id("r").startswith("ESR:")
    assert M.dependency_id("r", "d").startswith("ESD:")
    assert M.snapshot_id("s", "sc", "t").startswith("ESN:")
    assert M.report_id("s", "sc", "t").startswith("ESO:")


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
    forbidden = ("def execute", "def trade", "def deploy", "def allocate", "def promote_live",
                 "def place_order", "def modify_permission", "def change_permission",
                 "def run_live")
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
    import jarvis.autonomous_experiment_scheduler.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_aes_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    e.assign_priority(r1, 5, "", T[2], commit=True)
    e.create_scheduling_policy(sch, "p", "r", T[3], commit=True)
    e.update_schedule_state(r1, Q_QUEUED, "", T[4], commit=True)
    e.build_execution_plan(sch, "SCHEDULABLE", T[5], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("aes_"), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("experiment_manager", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("exm_experiments.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"event_id": "E1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("experiment_manager", "E1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_experiment_scheduler.__main__ import main
    assert main(["summary"]) == 0
    assert "schedule_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_experiment_scheduler.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_experiment_scheduler.__main__ import main
    main(["schedule", "--name", "q", "--commit"])
    sch = json.loads(capsys.readouterr().out)["schedule"]["schedule_id"]
    main(["request", "--schedule", sch, "--experiment", "EXP1", "--commit"])
    req = json.loads(capsys.readouterr().out)["request"]["request_id"]
    main(["priority", "--request", req, "--priority", "5", "--commit"])
    capsys.readouterr()
    assert main(["advance", "--request", req, "--to", "QUEUED", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == "QUEUED"


def test_cli_plan(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_experiment_scheduler.__main__ import main
    main(["schedule", "--name", "q", "--commit"])
    sch = json.loads(capsys.readouterr().out)["schedule"]["schedule_id"]
    main(["request", "--schedule", sch, "--experiment", "EXP1", "--commit"])
    req = json.loads(capsys.readouterr().out)["request"]["request_id"]
    main(["advance", "--request", req, "--to", "QUEUED", "--commit"])
    capsys.readouterr()
    assert main(["plan", "--schedule", sch, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert req in out["plan"]["plan"]


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_experiment_scheduler.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_depend_and_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_experiment_scheduler.__main__ import main
    main(["schedule", "--name", "q", "--commit"])
    sch = json.loads(capsys.readouterr().out)["schedule"]["schedule_id"]
    main(["request", "--schedule", sch, "--experiment", "EXP1", "--commit"])
    r1 = json.loads(capsys.readouterr().out)["request"]["request_id"]
    main(["request", "--schedule", sch, "--experiment", "EXP2", "--commit"])
    r2 = json.loads(capsys.readouterr().out)["request"]["request_id"]
    assert main(["depend", "--request", r2, "--on", r1, "--commit"]) == 0
    capsys.readouterr()
    assert main(["report", "--schedule", sch, "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["is_binding"] is False


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("target", list(_STATE_SEQ))
def test_each_state_reachable(tmp_path, monkeypatch, target):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    _advance_to(e, req, target)
    assert e.current_state(req) == target


@pytest.mark.parametrize("i,frm", list(enumerate(SCHEDULE_STATES)))
def test_state_membership(i, frm):
    assert frm in SCHEDULE_STATES


@pytest.mark.parametrize("prio", [0, 1, 5, 10, 99, -3])
def test_assign_various_priorities(tmp_path, monkeypatch, prio):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e, exp=f"EXP{prio}")
    p = e.assign_priority(req, prio, "", T[2], commit=True)
    assert p.priority == prio


def test_priority_id_one_per_request(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r1 = _request(e, exp="A")
    r2 = _request(e, exp="B", now=T[2])
    assert M.priority_id(r1) != M.priority_id(r2)


def test_dependency_id_deterministic():
    assert M.dependency_id("r", "d") == M.dependency_id("r", "d")


def test_build_plan_multiple_roots(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    reqs = []
    for i in range(4):
        r = e.register_experiment_request(sch, f"EXP{i}", "", T[1 + i], commit=True).request_id
        e.update_schedule_state(r, Q_QUEUED, "", T[10 + i], commit=True)
        reqs.append(r)
    plan = e.build_execution_plan(sch, "SCHEDULABLE", T[20], commit=True).plan
    assert sorted(plan) == sorted(reqs)


def test_build_plan_empty_schedule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    plan = e.build_execution_plan(sch, "SCHEDULABLE", T[5], commit=True)
    assert plan.plan == []


def test_build_plan_unknown_schedule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownScheduleError):
        e.build_execution_plan("ESG:ghost", "SCHEDULABLE", T[5], commit=True)


def test_snapshot_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    e.update_schedule_state(r1, Q_QUEUED, "", T[2], commit=True)
    snap = e.build_execution_plan(sch, "SCHEDULABLE", T[3], commit=True)
    assert snap.state_distribution.get(Q_QUEUED) == 1


def test_resolve_dependencies_unknown_request(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownRequestError):
        e.resolve_dependencies("ESQ:ghost", [], T[3], commit=True)


def test_assign_priority_unknown_request(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownRequestError):
        e.assign_priority("ESQ:ghost", 5, "", T[3], commit=True)


def test_policy_unknown_schedule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownScheduleError):
        e.create_scheduling_policy("ESG:ghost", "p", "r", T[1], commit=True)


def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    e.register_experiment_request(sch, "EXP1", "", T[1], commit=False)
    assert ledger.read_schedule_events() == []


def test_multiple_deps_at_once(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "A", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "B", "", T[2], commit=True).request_id
    r3 = e.register_experiment_request(sch, "C", "", T[3], commit=True).request_id
    deps = e.resolve_dependencies(r3, [r1, r2], T[4], commit=True)
    assert len(deps) == 2


def test_transition_events_valid_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    for ev in ledger.request_events(req):
        assert "to_state" in ev


def test_snapshot_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    a = e.build_execution_plan(sch, "SCHEDULABLE", T[5], commit=False)
    b = e.build_execution_plan(sch, "SCHEDULABLE", T[5], commit=False)
    assert a.snapshot_id == b.snapshot_id


def test_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    _advance_to(e, req, Q_ARCHIVED)
    with pytest.raises(IllegalScheduleTransition):
        e.update_schedule_state(req, Q_QUEUED, "", T[30], commit=True)


def test_report_scheduled_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "EXP1", "", T[1], commit=True).request_id
    _advance_to(e, r1, Q_SCHEDULED, start_t=2)
    rep = e.generate_schedule_report(sch, "ALL", T[20], commit=True)
    assert rep.scheduled_count == 1


def test_dependency_records_immutable_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "A", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "B", "", T[2], commit=True).request_id
    e.resolve_dependencies(r2, [r1], T[3], commit=True)
    e.resolve_dependencies(r2, [r1], T[4], commit=True)
    assert len(ledger.read_dependencies()) == 1


def test_topological_order_stable_across_calls():
    nodes = ["c", "a", "b"]
    edges = [("b", "a"), ("c", "b")]
    assert M.topological_order(nodes, edges, {}) == M.topological_order(nodes, edges, {})


@pytest.mark.parametrize("exp", ["EXP_A", "EXP_B", "EXP_C", "EXP_D", "EXP_E"])
def test_register_many_experiments(tmp_path, monkeypatch, exp):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r = e.register_experiment_request(sch, exp, "", T[1], commit=True)
    assert r.experiment_ref == exp


@pytest.mark.parametrize("name", ["q1", "q2", "q3"])
def test_multiple_schedules(tmp_path, monkeypatch, name):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = e.create_schedule(name, "m", T[0], commit=True)
    assert s.name == name


def test_schedule_requests_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s1 = e.create_schedule("s1", "m", T[0], commit=True).schedule_id
    s2 = e.create_schedule("s2", "m", T[0], commit=True).schedule_id
    e.register_experiment_request(s1, "E1", "", T[1], commit=True)
    e.register_experiment_request(s2, "E2", "", T[2], commit=True)
    assert len(ledger.schedule_requests(s1)) == 1


def test_priority_rule_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    req = _request(e)
    p = e.assign_priority(req, 7, "deadline_based", T[2], commit=True)
    assert p.rule == "deadline_based"


def test_dependency_record_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r1 = e.register_experiment_request(sch, "A", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "B", "", T[2], commit=True).request_id
    d = e.resolve_dependencies(r2, [r1], T[3], commit=True)[0]
    assert d.request_id == r2 and d.depends_on == r1


def test_request_meta_experiment_ref(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e)
    r = e.register_experiment_request(sch, "EXPZ", "", T[1], commit=True).request_id
    assert e._request_meta(r)["experiment_ref"] == "EXPZ"


def test_verify_all_ledgers_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _request(e)
    res = verify_chain()
    assert ledger.SCHEDULES[0] in res["ledgers"]


# ══════════════ end-to-end ══════════════
def test_end_to_end_scheduling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sch = _schedule(e, "main_queue")
    r1 = e.register_experiment_request(sch, "EXP_ingest", "", T[1], commit=True).request_id
    r2 = e.register_experiment_request(sch, "EXP_backtest", "", T[2], commit=True).request_id
    r3 = e.register_experiment_request(sch, "EXP_review", "", T[3], commit=True).request_id
    e.assign_priority(r1, 10, "critical", T[4], commit=True)
    e.assign_priority(r2, 5, "", T[5], commit=True)
    e.resolve_dependencies(r2, [r1], T[6], commit=True)
    e.resolve_dependencies(r3, [r2], T[7], commit=True)
    for r in (r1, r2, r3):
        e.update_schedule_state(r, Q_QUEUED, "", T[8], commit=True)
    plan = e.build_execution_plan(sch, "SCHEDULABLE", T[9], commit=True).plan
    assert plan.index(r1) < plan.index(r2) < plan.index(r3)
    e.create_scheduling_policy(sch, "resource_cap", "max 4 concurrent", T[10], commit=True)
    rep = e.generate_schedule_report(sch, "ALL", T[11], commit=True)
    assert rep.request_count == 3
    assert rep.dependency_count == 2
    assert verify_chain()["ok"] is True
