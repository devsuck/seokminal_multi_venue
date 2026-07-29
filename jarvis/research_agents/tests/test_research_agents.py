"""P11.1 Research Agent Framework 테스트. **연구 보조 AI 에이전트 — 읽기·분석·리포트 전용.**

에이전트 등록(불변·5종)·프로파일(역량·불변)·권한 가드(READ/ANALYZE/REPORT 허용, TRADE/EXECUTE/DEPLOY/ALLOCATE
차단·감사)·에이전트 생애주기(REGISTERED→ACTIVE→IDLE→RETIRED)·태스크 생애주기(CREATED→ASSIGNED→IN_PROGRESS→
COMPLETED/FAILED/CANCELLED)·메시지·리포트(REPORT 역량 필요)·활동 감사 원장·Research OS READ ONLY·verify(체인/변조/
중복/태스크/권한)·replay·CLI·보안(금지import·실행/거래/배포/할당 없음·금지 행위 차단·상위 원장 무변경·삭제 API
없음·불변·ASSIST≠EXECUTE·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_agents import ledger
from jarvis.research_agents import models as M
from jarvis.research_agents.engine import ResearchAgentEngine
from jarvis.research_agents.models import (
    AGENT_ACTIVE,
    AGENT_BACKTEST,
    AGENT_DATA_ANALYST,
    AGENT_IDLE,
    AGENT_REGISTERED,
    AGENT_RETIRED,
    AGENT_REVIEWER,
    AGENT_RISK,
    AGENT_STRATEGY,
    AGENT_TYPES,
    CapabilityDenied,
    ForbiddenAgentAction,
    IllegalAgentTransition,
    IllegalTaskTransition,
    ImmutableAgentError,
    ImmutableProfileError,
    ImmutableReportError,
    InvalidAgentType,
    InvalidCapability,
    TASK_ASSIGNED,
    TASK_COMPLETED,
    TASK_CREATED,
    TASK_IN_PROGRESS,
    UnknownAgentError,
)

T0 = "2026-07-24T00:00:00Z"
T1 = "2026-07-24T00:01:00Z"
T2 = "2026-07-24T00:02:00Z"
T3 = "2026-07-24T00:03:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_agents.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchAgentEngine()


def _agent(e, name="analyst", atype=AGENT_DATA_ANALYST, caps=("READ", "ANALYZE", "REPORT"),
           now=T0):
    e.register_agent(name, atype, "", now, commit=True)
    e.create_profile(name, list(caps), "", now, commit=True)
    return name


def _seed(sp, filename, rows):
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ══════════════ register_agent ══════════════
def test_register_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_agent("data1", AGENT_DATA_ANALYST, "", T0, commit=True)
    assert a.agent_id.startswith("RGA:")
    assert a.agent_type == AGENT_DATA_ANALYST


def test_register_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_agent("x", AGENT_RISK, now=T0, commit=False)
    b = _eng().register_agent("x", AGENT_RISK, now=T1, commit=False)
    assert a.agent_id == b.agent_id


def test_register_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_agent("x", AGENT_RISK, now=T0, commit=True)
    assert len(ledger.read_agents()) == 1


def test_register_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_agent("x", AGENT_RISK, now=T0, commit=False)
    assert ledger.read_agents() == []


def test_register_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidAgentType):
        _eng().register_agent("x", "TRADER", now=T0, commit=True)


@pytest.mark.parametrize("atype", list(AGENT_TYPES))
def test_register_all_five_types(tmp_path, monkeypatch, atype):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_agent(f"a_{atype}", atype, now=T0, commit=True)
    assert a.agent_type == atype


def test_register_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_RISK, now=T0, commit=True)
    e.register_agent("x", AGENT_RISK, now=T1, commit=True)
    assert len(ledger.read_agents()) == 1


def test_register_immutable_type_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_RISK, now=T0, commit=True)
    with pytest.raises(ImmutableAgentError):
        e.register_agent("x", AGENT_REVIEWER, now=T1, commit=True)


def test_register_logs_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_agent("x", AGENT_RISK, now=T0, commit=True)
    kinds = [a["kind"] for a in ledger.read_activity()]
    assert M.ACT_KIND_REGISTERED in kinds


def test_five_agent_types():
    assert len(AGENT_TYPES) == 5


# ══════════════ create_profile ══════════════
def test_profile_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_DATA_ANALYST, now=T0, commit=True)
    p = e.create_profile("x", ["READ", "ANALYZE"], "", T0, commit=True)
    assert p.profile_id.startswith("RGP:")
    assert p.capabilities == ["ANALYZE", "READ"]


def test_profile_unknown_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownAgentError):
        _eng().create_profile("ghost", ["READ"], now=T0, commit=True)


def test_profile_rejects_forbidden_capability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_DATA_ANALYST, now=T0, commit=True)
    with pytest.raises(ForbiddenAgentAction):
        e.create_profile("x", ["READ", "TRADE"], now=T0, commit=True)


def test_profile_forbidden_logs_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_DATA_ANALYST, now=T0, commit=True)
    with pytest.raises(ForbiddenAgentAction):
        e.create_profile("x", ["EXECUTE"], now=T0, commit=True)
    assert any(a["kind"] == M.ACT_KIND_BLOCKED for a in ledger.read_activity())


def test_profile_rejects_invalid_capability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_DATA_ANALYST, now=T0, commit=True)
    with pytest.raises(InvalidCapability):
        e.create_profile("x", ["FLY"], now=T0, commit=True)


def test_profile_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_DATA_ANALYST, now=T0, commit=True)
    e.create_profile("x", ["READ"], now=T0, commit=True)
    with pytest.raises(ImmutableProfileError):
        e.create_profile("x", ["READ", "ANALYZE"], now=T1, commit=True)


def test_profile_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_DATA_ANALYST, now=T0, commit=True)
    e.create_profile("x", ["READ"], now=T0, commit=True)
    e.create_profile("x", ["READ"], now=T1, commit=True)
    assert len(ledger.read_profiles()) == 1


def test_has_capability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x", caps=("READ", "ANALYZE"))
    assert e.has_capability("x", "READ") is True
    assert e.has_capability("x", "REPORT") is False


# ══════════════ guard_action (capability restrictions + forbidden blocked) ══════════════
@pytest.mark.parametrize("action", ["READ", "ANALYZE", "REPORT"])
def test_guard_allows_capabilities(tmp_path, monkeypatch, action):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    assert e.guard_action("x", action, T0, commit=True) is True


@pytest.mark.parametrize("action", ["TRADE", "EXECUTE", "DEPLOY", "ALLOCATE"])
def test_guard_blocks_forbidden(tmp_path, monkeypatch, action):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    with pytest.raises(ForbiddenAgentAction):
        e.guard_action("x", action, T0, commit=True)


@pytest.mark.parametrize("action", ["TRADE", "EXECUTE", "DEPLOY", "ALLOCATE"])
def test_guard_forbidden_audited(tmp_path, monkeypatch, action):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    with pytest.raises(ForbiddenAgentAction):
        e.guard_action("x", action, T0, commit=True)
    blocked = e.blocked_actions()
    assert len(blocked) == 1
    assert blocked[0]["allowed"] is False
    assert blocked[0]["action"] == action


def test_guard_capability_denied(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x", caps=("READ",))
    with pytest.raises(CapabilityDenied):
        e.guard_action("x", "REPORT", T0, commit=True)


def test_guard_invalid_capability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    with pytest.raises(InvalidCapability):
        e.guard_action("x", "FLY", T0, commit=True)


def test_guard_unknown_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownAgentError):
        _eng().guard_action("ghost", "READ", T0, commit=True)


def test_is_forbidden_action_fn():
    for a in ("TRADE", "EXECUTE", "DEPLOY", "ALLOCATE", "order", "liquidate"):
        assert M.is_forbidden_action(a) is True
    for a in ("READ", "ANALYZE", "REPORT"):
        assert M.is_forbidden_action(a) is False


def test_forbidden_actions_constant():
    assert set(M.FORBIDDEN_ACTIONS) == {"TRADE", "EXECUTE", "DEPLOY", "ALLOCATE"}


def test_allowed_capabilities_constant():
    assert set(M.ALLOWED_CAPABILITIES) == {"READ", "ANALYZE", "REPORT"}


# ══════════════ 에이전트 생애주기 ══════════════
def test_agent_initial_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    assert e.current_agent_state("x") == AGENT_REGISTERED


def test_agent_activate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.transition_agent("x", AGENT_ACTIVE, T1, commit=True)
    assert e.current_agent_state("x") == AGENT_ACTIVE


def test_agent_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.transition_agent("x", AGENT_ACTIVE, T1, commit=True)
    e.transition_agent("x", AGENT_IDLE, T2, commit=True)
    e.transition_agent("x", AGENT_ACTIVE, T3, commit=True)
    e.transition_agent("x", AGENT_RETIRED, "2026-07-24T00:04:00Z", commit=True)
    assert e.current_agent_state("x") == AGENT_RETIRED


def test_agent_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    with pytest.raises(IllegalAgentTransition):
        e.transition_agent("x", AGENT_IDLE, T1, commit=True)  # REGISTERED->IDLE 불가


def test_agent_retired_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.transition_agent("x", AGENT_ACTIVE, T1, commit=True)
    e.transition_agent("x", AGENT_RETIRED, T2, commit=True)
    with pytest.raises(IllegalAgentTransition):
        e.transition_agent("x", AGENT_ACTIVE, T3, commit=True)


def test_agent_transition_logs_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.transition_agent("x", AGENT_ACTIVE, T1, commit=True)
    assert any(a["kind"] == M.ACT_KIND_AGENT_TRANSITION for a in ledger.read_activity())


def test_can_transition_agent_fn():
    assert M.can_transition_agent(AGENT_REGISTERED, AGENT_ACTIVE) is True
    assert M.can_transition_agent(AGENT_REGISTERED, AGENT_IDLE) is False


# ══════════════ 태스크 생애주기 ══════════════
def test_task_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "ANALYZE", "dataset_1", "check nulls", T0, commit=True)
    assert t.task_id.startswith("RGT:")
    assert t.to_state == TASK_CREATED


def test_task_forbidden_action_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    with pytest.raises(ForbiddenAgentAction):
        e.create_task("x", "TRADE", "AAPL", "buy", T0, commit=True)
    assert len(ledger.read_tasks()) == 0
    assert len(e.blocked_actions()) == 1


def test_task_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    tid = t.task_id
    e.assign_task(tid, T1, commit=True)
    e.start_task(tid, T2, commit=True)
    e.complete_task(tid, T3, commit=True)
    assert e.current_task_state(tid) == TASK_COMPLETED


def test_task_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    with pytest.raises(IllegalTaskTransition):
        e.complete_task(t.task_id, T1, commit=True)  # CREATED->COMPLETED 불가


def test_task_fail_path(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    e.assign_task(t.task_id, T1, commit=True)
    e.start_task(t.task_id, T2, commit=True)
    e.fail_task(t.task_id, T3, commit=True)
    assert e.current_task_state(t.task_id) == "FAILED"


def test_task_cancel_path(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "READ", "d1", "desc", T0, commit=True)
    e.cancel_task(t.task_id, T1, commit=True)
    assert e.current_task_state(t.task_id) == "CANCELLED"


def test_task_completed_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    e.assign_task(t.task_id, T1, commit=True)
    e.start_task(t.task_id, T2, commit=True)
    e.complete_task(t.task_id, T3, commit=True)
    with pytest.raises(IllegalTaskTransition):
        e.fail_task(t.task_id, "2026-07-24T00:05:00Z", commit=True)


def test_task_create_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    e.create_task("x", "ANALYZE", "d1", "desc", T1, commit=True)
    # 같은 task 는 CREATED 이벤트 1개만
    created = [t for t in ledger.read_tasks() if t["to_state"] == TASK_CREATED]
    assert len(created) == 1


def test_task_event_logs_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    assert any(a["kind"] == M.ACT_KIND_TASK_EVENT for a in ledger.read_activity())


def test_can_transition_task_fn():
    assert M.can_transition_task(TASK_CREATED, TASK_ASSIGNED) is True
    assert M.can_transition_task(TASK_CREATED, TASK_COMPLETED) is False


def test_six_task_states():
    assert len(M.TASK_STATES) == 6


# ══════════════ 메시지 ══════════════
def test_message_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "a")
    _agent(e, "b", "b_agent" if False else AGENT_REVIEWER)
    m = e.send_message("a", "b", "hello", "please review", T0, commit=True)
    assert m.message_id.startswith("RGM:")
    assert m.from_agent == "a"


def test_message_unknown_sender(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownAgentError):
        _eng().send_message("ghost", "b", "s", "c", T0, commit=True)


def test_message_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "a")
    e.send_message("a", "b", "s", "c1", T0, commit=True)
    # 동일 id(from,to,subject,content) 는 idempotent; 내용이 다르면 다른 id
    m2 = e.send_message("a", "b", "s", "c1", T1, commit=True)
    assert len(ledger.read_messages()) == 1
    assert m2.content == "c1"


def test_message_logs_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "a")
    e.send_message("a", "b", "s", "c", T0, commit=True)
    assert any(a["kind"] == M.ACT_KIND_MESSAGE for a in ledger.read_activity())


# ══════════════ 리포트 ══════════════
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    r = e.submit_report("x", "task1", "GLOBAL", ["finding1"], "ok", T0, commit=True)
    assert r.report_id.startswith("RGR:")
    assert r.findings == ["finding1"]


def test_report_requires_report_capability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x", caps=("READ", "ANALYZE"))  # no REPORT
    with pytest.raises(CapabilityDenied):
        e.submit_report("x", "task1", "GLOBAL", [], "", T0, commit=True)


def test_report_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.submit_report("x", "task1", "GLOBAL", ["f1"], "s1", T0, commit=True)
    with pytest.raises(ImmutableReportError):
        e.submit_report("x", "task1", "GLOBAL", ["f2"], "s2", T1, commit=True)


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.submit_report("x", "task1", "GLOBAL", ["f1"], "s1", T0, commit=True)
    e.submit_report("x", "task1", "GLOBAL", ["f1"], "s1", T1, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_logs_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.submit_report("x", "task1", "GLOBAL", [], "", T0, commit=True)
    assert any(a["kind"] == M.ACT_KIND_REPORT for a in ledger.read_activity())


# ══════════════ Research OS READ ONLY ══════════════
def test_read_os(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "dg_datasets.jsonl", [{"dataset_hash": "d1"}, {"dataset_hash": "d2"}])
    e = _eng()
    _agent(e, "x")
    assert len(e.read_os("data")) == 2


def test_analyze_source(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "ai_signals.jsonl", [{"signal_hash": "s1"}])
    e = _eng()
    _agent(e, "x", AGENT_STRATEGY)
    res = e.analyze_source("x", "alpha", T0, commit=True)
    assert res["record_count"] == 1
    assert res["read_only"] is True


def test_analyze_requires_analyze_capability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x", caps=("READ",))
    with pytest.raises(CapabilityDenied):
        e.analyze_source("x", "alpha", T0, commit=True)


def test_source_never_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "ki_insights.jsonl", [{"insight_id": "i1"}])
    before = open(sp("ki_insights.jsonl")).read()
    e = _eng()
    _agent(e, "x")
    e.analyze_source("x", "knowledge", T0, commit=True)
    e.read_os("knowledge")
    assert open(sp("ki_insights.jsonl")).read() == before


def test_only_ragt_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    e.assign_task(t.task_id, T1, commit=True)
    e.send_message("x", "y", "s", "c", T1, commit=True)
    e.submit_report("x", "task1", "GLOBAL", [], "", T1, commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("ragt_"), fn


# ══════════════ 활동 감사 원장 ══════════════
def test_activity_records_all_ops(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")  # register + profile
    t = e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    e.assign_task(t.task_id, T1, commit=True)
    e.send_message("x", "y", "s", "c", T1, commit=True)
    e.submit_report("x", "task1", "GLOBAL", [], "", T1, commit=True)
    kinds = {a["kind"] for a in ledger.read_activity()}
    assert {M.ACT_KIND_REGISTERED, M.ACT_KIND_PROFILE, M.ACT_KIND_TASK_EVENT, M.ACT_KIND_MESSAGE,
            M.ACT_KIND_REPORT} <= kinds


def test_agent_activity_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "a")
    _agent(e, "b", AGENT_RISK)
    assert len(e.agent_activity("a")) >= 1
    assert all(x["agent"] == "a" for x in e.agent_activity("a"))


def test_activity_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_RISK, now=T0, commit=False)
    assert ledger.read_activity() == []


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agents.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agents.verify import verify_chain
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    e.assign_task(t.task_id, T1, commit=True)
    e.start_task(t.task_id, T2, commit=True)
    e.complete_task(t.task_id, T3, commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_RISK, now=T0, commit=True)
    p = sp("ragt_agents.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["agent_type"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_agents.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_verify_task_lifecycle_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agents.verify import task_lifecycle_integrity
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    e.assign_task(t.task_id, T1, commit=True)
    assert task_lifecycle_integrity()["ok"] is True


def test_verify_permission_boundary_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agents.verify import permission_boundary
    e = _eng()
    _agent(e, "x")
    with pytest.raises(ForbiddenAgentAction):
        e.guard_action("x", "TRADE", T0, commit=True)
    # 차단 기록은 allowed=False 이므로 경계 OK
    assert permission_boundary()["ok"] is True


def test_verify_permission_boundary_detects_forged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    # 원장에 금지 행위를 allowed=True 로 위조 삽입
    e._log("TASK_EVENT", "x", "TRADE", "forged", "forged", True, T1, commit=True)
    from jarvis.research_agents.verify import permission_boundary
    assert permission_boundary()["ok"] is False


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agents.verify import replay
    e = _eng()
    _agent(e, "x")
    assert replay(e, T1)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=True)
    e.submit_report("x", "task1", "GLOBAL", [], "", T0, commit=True)
    s = e.summary(T2)
    assert s.agent_count == 1
    assert s.profile_count == 1
    assert s.report_count == 1


def test_summary_blocked_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    with pytest.raises(ForbiddenAgentAction):
        e.guard_action("x", "EXECUTE", T0, commit=True)
    assert e.summary(T1).blocked_count == 1


# ══════════════ query helpers ══════════════
def test_list_agents_by_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "a", AGENT_DATA_ANALYST)
    _agent(e, "b", AGENT_RISK)
    assert e.list_agents(AGENT_RISK) == ["b"]
    assert sorted(e.list_agents()) == ["a", "b"]


# ══════════════ 보안 / 불변식 ══════════════
def test_no_forbidden_imports():
    import ast
    forbidden = ("execution", "broker", "order", "portfolio_execution", "capital_allocation",
                 "live_trading", "permission", "risk_controller")
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
                for fb in forbidden:
                    assert not (m == f"jarvis.{fb}" or m.startswith(f"jarvis.{fb}.")), (fn, m)


def test_engine_no_execution_methods():
    e = ResearchAgentEngine()
    for bad in ("execute", "trade", "deploy", "allocate", "place_order", "submit_order",
                "activate", "liquidate", "rebalance", "modify_config"):
        assert not hasattr(e, bad), bad


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


def test_no_execution_verbs_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def execute", "def trade", "def deploy", "def allocate", "def place_order"):
            assert bad not in src, (fn, bad)


def test_disclaimer_marks_assist_only():
    from jarvis.research_agents.engine import _DISCLAIMER
    assert "ASSIST ≠ EXECUTE" in _DISCLAIMER
    assert "REPORT ≠ DEPLOY" in _DISCLAIMER


def test_records_frozen():
    a = M.AgentRecord(agent_id="RGA:x", name="a", agent_type="RISK_ANALYST", description="",
                      registered_at=T0)
    with pytest.raises(Exception):
        a.name = "b"  # type: ignore


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.agent_id("x")[:4], M.profile_id("x")[:4], M.task_id("a", "b", "c", "d")[:4],
           M.task_event_id("t", "s")[:4], M.message_id("a", "b", "s", "c")[:4],
           M.report_id("a", "t", "s")[:4], M.activity_id("k", "r", T0)[:4]}
    assert len(ids) == 7


def test_six_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 6
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 6
    assert all(f.startswith("ragt_") for f in fns)


def test_seven_activity_kinds():
    assert len(M.ACTIVITY_KINDS) == 7


def test_four_agent_states():
    assert len(M.AGENT_STATES) == 4


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_agent_default_source_map():
    for atype in AGENT_TYPES:
        assert atype in ledger.AGENT_DEFAULT_SOURCE


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_agents.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_register(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["register", "--name", "x", "--type", "RISK_ANALYST", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["agent"]["agent_type"] == "RISK_ANALYST"


def test_cli_profile(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "x", "--type", "RISK_ANALYST", "--commit"], capsys)
    rc, out = _run(["profile", "--agent", "x", "--caps", "READ,ANALYZE", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["profile"]["capabilities"] == ["ANALYZE", "READ"]


def test_cli_task_and_advance(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "x", "--type", "DATA_ANALYST", "--commit"], capsys)
    _run(["profile", "--agent", "x", "--caps", "READ,ANALYZE,REPORT", "--commit"], capsys)
    rc, out = _run(["task", "--agent", "x", "--action", "ANALYZE", "--target", "d1",
                    "--desc", "z", "--commit"], capsys)
    assert rc == 0
    tid = json.loads(out)["task"]["task_id"]
    rc2, out2 = _run(["advance", "--task", tid, "--to", "ASSIGNED", "--commit"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["task"]["to_state"] == "ASSIGNED"


def test_cli_guard_blocks_forbidden(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "x", "--type", "DATA_ANALYST", "--commit"], capsys)
    _run(["profile", "--agent", "x", "--caps", "READ,ANALYZE,REPORT", "--commit"], capsys)
    rc, out = _run(["guard", "--agent", "x", "--action", "TRADE"], capsys)
    assert rc == 1
    assert json.loads(out)["blocked"] is True


def test_cli_guard_allows(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "x", "--type", "DATA_ANALYST", "--commit"], capsys)
    _run(["profile", "--agent", "x", "--caps", "READ,ANALYZE,REPORT", "--commit"], capsys)
    rc, out = _run(["guard", "--agent", "x", "--action", "READ"], capsys)
    assert rc == 0
    assert json.loads(out)["allowed"] is True


def test_cli_message(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "a", "--type", "DATA_ANALYST", "--commit"], capsys)
    rc, out = _run(["message", "--from", "a", "--to", "b", "--subject", "s",
                    "--content", "c", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["message"]["from_agent"] == "a"


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "x", "--type", "REVIEWER", "--commit"], capsys)
    _run(["profile", "--agent", "x", "--caps", "READ,ANALYZE,REPORT", "--commit"], capsys)
    rc, out = _run(["report", "--agent", "x", "--task", "t1", "--scope", "G",
                    "--summary", "ok", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["report"]["summary"] == "ok"


def test_cli_agents(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "x", "--type", "RISK_ANALYST", "--commit"], capsys)
    rc, out = _run(["agents", "--type", "RISK_ANALYST"], capsys)
    assert rc == 0
    assert "x" in json.loads(out)["agents"]


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "x", "--type", "RISK_ANALYST", "--commit"], capsys)
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "agent_count" in json.loads(out)


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("atype,role", list(ledger.AGENT_DEFAULT_SOURCE.items()))
def test_each_type_default_source_reads(tmp_path, monkeypatch, atype, role):
    sp = _iso(tmp_path, monkeypatch)
    spec = ledger.SOURCE_LEDGERS[role]
    _seed(sp, spec[0], [{"x": 1}])
    e = _eng()
    _agent(e, f"a_{atype}", atype)
    assert len(e.read_os(role)) == 1


@pytest.mark.parametrize("cap", ["READ", "ANALYZE", "REPORT"])
def test_profile_accepts_each_allowed_cap(tmp_path, monkeypatch, cap):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_DATA_ANALYST, now=T0, commit=True)
    p = e.create_profile("x", [cap], now=T0, commit=True)
    assert cap in p.capabilities


@pytest.mark.parametrize("bad", ["TRADE", "EXECUTE", "DEPLOY", "ALLOCATE", "ORDER", "LIQUIDATE"])
def test_profile_rejects_each_forbidden_cap(tmp_path, monkeypatch, bad):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_agent("x", AGENT_DATA_ANALYST, now=T0, commit=True)
    with pytest.raises(ForbiddenAgentAction):
        e.create_profile("x", ["READ", bad], now=T0, commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (TASK_CREATED, TASK_ASSIGNED, True), (TASK_CREATED, "CANCELLED", True),
    (TASK_ASSIGNED, TASK_IN_PROGRESS, True), (TASK_IN_PROGRESS, TASK_COMPLETED, True),
    (TASK_IN_PROGRESS, "FAILED", True), (TASK_CREATED, TASK_COMPLETED, False),
    (TASK_ASSIGNED, TASK_COMPLETED, False), (TASK_COMPLETED, TASK_ASSIGNED, False),
])
def test_task_transition_matrix(frm, to, ok):
    assert M.can_transition_task(frm, to) is ok


@pytest.mark.parametrize("frm,to,ok", [
    (AGENT_REGISTERED, AGENT_ACTIVE, True), (AGENT_ACTIVE, AGENT_IDLE, True),
    (AGENT_IDLE, AGENT_ACTIVE, True), (AGENT_ACTIVE, AGENT_RETIRED, True),
    (AGENT_IDLE, AGENT_RETIRED, True), (AGENT_REGISTERED, AGENT_RETIRED, False),
    (AGENT_RETIRED, AGENT_ACTIVE, False),
])
def test_agent_transition_matrix(frm, to, ok):
    assert M.can_transition_agent(frm, to) is ok


def test_task_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.create_task("x", "ANALYZE", "d1", "desc", T0, commit=False)
    assert ledger.read_tasks() == []


def test_report_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.submit_report("x", "t", "G", [], "", T0, commit=False)
    assert ledger.read_reports() == []


def test_message_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    e.send_message("x", "y", "s", "c", T0, commit=False)
    assert ledger.read_messages() == []


def test_read_os_limit(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "dg_datasets.jsonl", [{"dataset_hash": f"d{i}"} for i in range(5)])
    e = _eng()
    _agent(e, "x")
    assert len(e.read_os("data", 2)) == 2


def test_read_os_missing_role(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().read_os("nonexistent") == []


def test_blocked_actions_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    assert e.blocked_actions() == []


def test_current_task_state_none(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_task_state("RGT:nonexistent") is None


def test_task_target_preserved_through_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    t = e.create_task("x", "ANALYZE", "target_z", "d", T0, commit=True)
    e.assign_task(t.task_id, T1, commit=True)
    evs = ledger.task_events(t.task_id)
    assert all(ev["target"] == "target_z" for ev in evs)


def test_activity_id_distinct_per_kind(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "x")
    ids = {a["activity_id"] for a in ledger.read_activity()}
    assert len(ids) == len(ledger.read_activity())  # 모두 고유


def test_all_agent_types_have_report_cap_path(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for i, atype in enumerate(AGENT_TYPES):
        _agent(e, f"ag{i}", atype)
        r = e.submit_report(f"ag{i}", "t", "G", [], "s", T0, commit=True)
        assert r.agent == f"ag{i}"


# ══════════════ 통합 시나리오 ══════════════
def test_end_to_end_research_assist(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "dg_datasets.jsonl", [{"dataset_hash": "d1"}])
    _seed(sp, "ai_signals.jsonl", [{"signal_hash": "s1"}])
    e = _eng()
    # 5종 에이전트 등록
    for name, atype in [("data", AGENT_DATA_ANALYST), ("strat", AGENT_STRATEGY),
                        ("bt", AGENT_BACKTEST), ("risk", AGENT_RISK), ("rev", AGENT_REVIEWER)]:
        e.register_agent(name, atype, "", T0, commit=True)
        e.create_profile(name, ["READ", "ANALYZE", "REPORT"], "", T0, commit=True)
        e.transition_agent(name, AGENT_ACTIVE, T1, commit=True)
    # Data Analyst: analyze + task + report
    e.analyze_source("data", "data", T1, commit=True)
    t = e.create_task("data", "ANALYZE", "dg_datasets", "quality", T1, commit=True)
    e.assign_task(t.task_id, T2, commit=True)
    e.start_task(t.task_id, T2, commit=True)
    e.complete_task(t.task_id, T3, commit=True)
    e.submit_report("data", t.task_id, "DATA", ["1 dataset"], "clean", T3, commit=True)
    e.send_message("data", "rev", "review", "please review", T3, commit=True)
    # forbidden 시도는 차단
    for a in ("TRADE", "EXECUTE", "DEPLOY", "ALLOCATE"):
        with pytest.raises(ForbiddenAgentAction):
            e.guard_action("strat", a, T3, commit=True)
    from jarvis.research_agents.verify import verify_chain
    v = verify_chain()
    assert v["ok"] is True
    assert v["permission"]["ok"] is True
    assert v["task_lifecycle"]["ok"] is True
    s = e.summary(T3)
    assert s.agent_count == 5
    assert s.blocked_count == 4
    assert s.report_count == 1
