"""P12.3 Research Agent Execution Coordinator 테스트. **조정·기록 전용.**

에이전트 배정·작업 위임(CREATED→ASSIGNED→IN_PROGRESS→HANDOFF→REVIEW→COMPLETED)·진행 추적·핸드오프(증거 필수)·
상충 소유 차단·완료 결과 필수·협업/충돌 해소·에이전트 계보·verify(체인/변조/중복/생애주기/상충소유/핸드오프증거/
완료결과/고아)·replay·CLI·보안(금지import·실행 없음·삭제 API 없음·불변·COORDINATE≠EXECUTION·rco_ 계층과 격리).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_agent_coordinator import ledger
from jarvis.research_agent_coordinator import models as M
from jarvis.research_agent_coordinator.engine import ResearchAgentCoordinatorEngine
from jarvis.research_agent_coordinator.models import (
    A_ASSIGNED,
    A_COMPLETED,
    A_CREATED,
    A_HANDOFF,
    A_IN_PROGRESS,
    A_REVIEW,
    ASSIGNMENT_STATES,
    ConflictingOwnerError,
    HandoffEvidenceError,
    IllegalAssignmentTransition,
    ImmutableAgentError,
    MissingResultError,
    UnknownAgentError,
    UnknownAssignmentError,
)
from jarvis.research_agent_coordinator.verify import (
    completion_integrity,
    handoff_integrity,
    lifecycle_integrity,
    orphan_integrity,
    ownership_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_agent_coordinator.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchAgentCoordinatorEngine()


def _coord(e, coord="coord1", agent="agentA", now=T[0]):
    e.assign_agent(coord, agent, "researcher", now, commit=True)
    return coord


def _assignment(e, coord="coord1", agent="agentA", task="TASK1", now=T[1]):
    if not ledger.agent_registered(coord, agent):
        e.assign_agent(coord, agent, "researcher", T[0], commit=True)
    return e.create_task_assignment(coord, task, agent, "", now, commit=True).assignment_id


def _to_review(e, aid, agent="agentA"):
    e.track_progress(aid, 50, "", "", T[3], commit=True)
    e.submit_for_review(aid, T[4], commit=True)
    return aid


# ══════════════ Phase 0 / 접두사 / 격리 ══════════════
def test_prefix_all_ledgers_rac():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rac_")


def test_six_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 6


def test_isolated_from_rco_layer():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    assert not any(n.startswith("rco_") for n in names)


def test_source_ledgers_named_four():
    for k in ("agent_governance", "research_organization", "autonomous_research_pipeline",
              "autonomous_experiment_scheduler"):
        assert k in ledger.SOURCE_LEDGERS


def test_six_lifecycle_states():
    assert len(ASSIGNMENT_STATES) == 6


# ══════════════ assign_agent ══════════════
def test_assign_agent_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.assign_agent("c1", "a1", "researcher", T[0], commit=True)
    assert r.agent_registration_id.startswith("ACA:")
    assert ledger.agent_registered("c1", "a1")


def test_assign_agent_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("c1", "a1", "r", T[0], commit=True)
    e.assign_agent("c1", "a1", "r", T[1], commit=True)
    assert len(ledger.read_agents()) == 1


def test_assign_agent_immutable_capability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("c1", "a1", "r1", T[0], commit=True)
    with pytest.raises(ImmutableAgentError):
        e.assign_agent("c1", "a1", "r2", T[1], commit=True)


def test_assign_agent_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("c1", "a1", "r", T[0], commit=False)
    assert ledger.read_agents() == []


# ══════════════ create_task_assignment ══════════════
def test_create_assignment_genesis_assigned(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    assert aid.startswith("ACO:")
    assert e.current_state(aid) == A_ASSIGNED
    assert e.current_owner(aid) == "agentA"


def test_create_assignment_requires_registered_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownAgentError):
        e.create_task_assignment("c1", "TASK1", "ghost", "", T[1], commit=True)


def test_create_assignment_records_created_then_assigned(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    states = [ev["to_state"] for ev in ledger.assignment_events(aid)]
    assert states == [A_CREATED, A_ASSIGNED]


def test_create_assignment_idempotent_same_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _coord(e)
    a1 = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.create_task_assignment("coord1", "TASK1", "agentA", "", T[2], commit=True)
    assert len(ledger.assignment_events(a1)) == 2


# ══════════════ conflicting owners ══════════════
def test_conflicting_owner_same_coordinator(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True)
    with pytest.raises(ConflictingOwnerError):
        e.create_task_assignment("coord1", "TASK1", "agentB", "", T[2], commit=True)


def test_conflicting_owner_cross_coordinator(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord2", "agentB", "r", T[0], commit=True)
    e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True)
    with pytest.raises(ConflictingOwnerError):
        e.create_task_assignment("coord2", "TASK1", "agentB", "", T[2], commit=True)


def test_no_conflict_after_completion(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord2", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 100, "", "", T[2], commit=True)
    e.submit_for_review(aid, T[3], commit=True)
    e.complete_assignment(aid, "RESULT1", T[4], commit=True)
    # 완료 후 다른 코디네이터에서 재배정 가능(상충 아님)
    a2 = e.create_task_assignment("coord2", "TASK1", "agentB", "", T[5], commit=True)
    assert a2.assignment_id != aid


# ══════════════ track_progress ══════════════
def test_track_progress_advances(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    e.track_progress(aid, 25, "started", "", T[3], commit=True)
    assert e.current_state(aid) == A_IN_PROGRESS


def test_track_progress_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    p = e.track_progress(aid, 50, "halfway", "", T[3], commit=True)
    assert p.progress_id.startswith("ACH:")
    assert p.percent == 50


def test_track_progress_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    e.track_progress(aid, 25, "", "", T[3], commit=True)
    e.track_progress(aid, 75, "", "", T[4], commit=True)
    assert len(ledger.assignment_progress(aid)) == 2


def test_track_progress_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownAssignmentError):
        e.track_progress("ACO:ghost", 10, "", "", T[3], commit=True)


# ══════════════ record_handoff (evidence required) ══════════════
def test_handoff_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    h = e.record_handoff(aid, "agentB", "EVID1", "", T[3], commit=True)
    assert h.handoff_id.startswith("ACN:")
    assert e.current_state(aid) == A_HANDOFF
    assert e.current_owner(aid) == "agentB"


def test_handoff_requires_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    with pytest.raises(HandoffEvidenceError):
        e.record_handoff(aid, "agentB", "", "", T[3], commit=True)


def test_handoff_to_unregistered_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    with pytest.raises(UnknownAgentError):
        e.record_handoff(aid, "ghost", "EVID1", "", T[3], commit=True)


def test_handoff_wrong_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    # ASSIGNED 상태에서 핸드오프 불가(IN_PROGRESS 필요)
    with pytest.raises(IllegalAssignmentTransition):
        e.record_handoff(aid, "agentB", "EVID1", "", T[3], commit=True)


def test_handoff_then_resume(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    e.record_handoff(aid, "agentB", "EVID1", "", T[3], commit=True)
    e.track_progress(aid, 80, "", "", T[4], commit=True)
    assert e.current_state(aid) == A_IN_PROGRESS
    assert e.current_owner(aid) == "agentB"


# ══════════════ completion (result required) ══════════════
def test_complete_success(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _to_review(e, _assignment(e))
    e.complete_assignment(aid, "RESULT1", T[10], commit=True)
    assert e.current_state(aid) == A_COMPLETED


def test_complete_requires_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _to_review(e, _assignment(e))
    with pytest.raises(MissingResultError):
        e.complete_assignment(aid, "", T[10], commit=True)


def test_complete_wrong_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    e.track_progress(aid, 40, "", "", T[3], commit=True)
    with pytest.raises(IllegalAssignmentTransition):
        e.complete_assignment(aid, "RESULT1", T[4], commit=True)


def test_completed_event_has_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _to_review(e, _assignment(e))
    e.complete_assignment(aid, "RESULT1", T[10], commit=True)
    comp = [ev for ev in ledger.assignment_events(aid) if ev["to_state"] == A_COMPLETED][0]
    assert comp["result_ref"] == "RESULT1"


def test_full_lifecycle_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 30, "", "", T[2], commit=True)
    e.record_handoff(aid, "agentB", "EVID1", "", T[3], commit=True)
    e.track_progress(aid, 80, "", "", T[4], commit=True)
    e.submit_for_review(aid, T[5], commit=True)
    e.complete_assignment(aid, "RESULT1", T[6], commit=True)
    states = [ev["to_state"] for ev in ledger.assignment_events(aid)]
    assert states == [A_CREATED, A_ASSIGNED, A_IN_PROGRESS, A_HANDOFF, A_IN_PROGRESS, A_REVIEW,
                      A_COMPLETED]


def test_completed_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _to_review(e, _assignment(e))
    e.complete_assignment(aid, "RESULT1", T[10], commit=True)
    with pytest.raises(IllegalAssignmentTransition):
        e.submit_for_review(aid, T[11], commit=True)


# ══════════════ resolve_assignment_conflict ══════════════
def test_resolve_conflict_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = e.resolve_assignment_conflict("TASK1", ["agentA", "agentB"], "agentA", "seniority", T[5],
                                      commit=True)
    assert c.collaboration_id.startswith("ACC:")
    assert c.winning_agent == "agentA"


def test_resolve_conflict_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.resolve_assignment_conflict("TASK1", ["a", "b"], "a", "", T[5], commit=True)
    e.resolve_assignment_conflict("TASK1", ["a", "c"], "c", "", T[6], commit=True)
    assert len(ledger.task_collaborations("TASK1")) == 2


# ══════════════ report ══════════════
def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    e.record_handoff(aid, "agentB", "EVID1", "", T[3], commit=True)
    rep = e.generate_coordination_report("coord1", "ALL", T[10], commit=True)
    assert rep.assignment_count == 1
    assert rep.handoff_count == 1
    assert rep.agent_count == 2


def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _coord(e)
    rep = e.generate_coordination_report("coord1", "ALL", T[1], commit=True)
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _coord(e)
    rep = e.generate_coordination_report("coord1", "ALL", T[1], commit=True)
    assert "COORDINATE ≠ EXECUTION" in rep.disclaimer


def test_report_completed_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _to_review(e, _assignment(e))
    e.complete_assignment(aid, "R1", T[10], commit=True)
    rep = e.generate_coordination_report("coord1", "ALL", T[11], commit=True)
    assert rep.completed_count == 1


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    e.record_handoff(aid, "agentB", "EVID1", "", T[3], commit=True)
    e.track_progress(aid, 80, "", "", T[4], commit=True)
    e.submit_for_review(aid, T[5], commit=True)
    e.complete_assignment(aid, "R1", T[6], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    p = ledger.state_path(ledger.OWNERSHIP[0])
    recs = ledger.read_ownership_events()
    recs[0]["agent"] = "TAMPERED"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    p = ledger.state_path(ledger.OWNERSHIP[0])
    recs = ledger.read_ownership_events()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.OWNERSHIP[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    p = ledger.state_path(ledger.OWNERSHIP[0])
    recs = ledger.read_ownership_events()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.OWNERSHIP[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _to_review(e, _assignment(e))
    assert lifecycle_integrity()["ok"] is True


def test_ownership_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    assert ownership_integrity()["ok"] is True


def test_ownership_integrity_conflict(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord2", "agentB", "r", T[0], commit=True)
    e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True)
    # coord2 배정 위조 주입(같은 task, 다른 owner, 활성)
    p = ledger.state_path(ledger.OWNERSHIP[0])
    recs = ledger.read_ownership_events()
    forged = dict(recs[0])
    forged["ownership_event_id"] = "ACV:forged00000"
    forged["assignment_id"] = "ACO:forged00000"
    forged["coordinator"] = "coord2"
    forged["agent"] = "agentB"
    forged["previous_hash"] = recs[-1]["record_hash"]
    forged["record_hash"] = M.content_hash(forged)
    with open(p, "a") as f:
        f.write(json.dumps(forged, ensure_ascii=False, default=str) + "\n")
    assert ownership_integrity()["ok"] is False


def test_handoff_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    e.record_handoff(aid, "agentB", "EVID1", "", T[3], commit=True)
    assert handoff_integrity()["ok"] is True


def test_handoff_integrity_missing_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    e.record_handoff(aid, "agentB", "EVID1", "", T[3], commit=True)
    p = ledger.state_path(ledger.HANDOFFS[0])
    recs = ledger.read_handoffs()
    recs[0]["evidence_ref"] = ""
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert handoff_integrity()["ok"] is False


def test_completion_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _to_review(e, _assignment(e))
    e.complete_assignment(aid, "R1", T[10], commit=True)
    assert completion_integrity()["ok"] is True


def test_completion_integrity_missing_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _to_review(e, _assignment(e))
    e.complete_assignment(aid, "R1", T[10], commit=True)
    p = ledger.state_path(ledger.OWNERSHIP[0])
    recs = ledger.read_ownership_events()
    for r in recs:
        if r["to_state"] == A_COMPLETED:
            r["result_ref"] = ""
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert completion_integrity()["ok"] is False


def test_orphan_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    assert orphan_integrity()["ok"] is True


def test_orphan_integrity_unrostered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    # 로스터에서 에이전트 제거
    p = ledger.state_path(ledger.REGISTRY[0])
    with open(p, "w") as f:
        f.write("")
    assert orphan_integrity()["ok"] is False


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    e.track_progress(aid, 10, "", "", T[3], commit=True)
    s = e.summary(T[9])
    assert s.agent_registration_count == 1
    assert s.progress_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_assignments_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    assert aid in e.assignments_in_state(A_ASSIGNED)


def test_list_assignments_by_coordinator(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    assert len(e.list_assignments("coord1")) == 1


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (A_CREATED, A_ASSIGNED, True),
    (A_ASSIGNED, A_IN_PROGRESS, True),
    (A_IN_PROGRESS, A_HANDOFF, True),
    (A_IN_PROGRESS, A_REVIEW, True),
    (A_HANDOFF, A_IN_PROGRESS, True),
    (A_HANDOFF, A_REVIEW, True),
    (A_REVIEW, A_COMPLETED, True),
    (A_REVIEW, A_IN_PROGRESS, True),
    (A_CREATED, A_COMPLETED, False),
    (A_ASSIGNED, A_REVIEW, False),
    (A_COMPLETED, A_IN_PROGRESS, False),
    (A_CREATED, A_IN_PROGRESS, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["EXECUTE_TRADE", "DEPLOY", "ALLOCATE", "MODIFY_PERMISSION",
                                  "EXECUTE", "TRADE", "PLACE_ORDER", "change_permission"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["ASSIGN", "COORDINATE", "HANDOFF", "TRACK", "DELEGATE", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.assignment_id("c", "t") == M.assignment_id("c", "t")
    assert M.agent_registration_id("c", "a") == M.agent_registration_id("c", "a")


def test_ids_prefixes_ac_scheme():
    assert M.agent_registration_id("c", "a").startswith("ACA:")
    assert M.assignment_id("c", "t").startswith("ACO:")
    assert M.ownership_event_id("a", "s", 0).startswith("ACV:")
    assert M.progress_id("a", 0).startswith("ACH:")
    assert M.handoff_id("a", 0).startswith("ACN:")
    assert M.collaboration_id("t", 0).startswith("ACC:")
    assert M.report_id("c", "s", "t").startswith("ACG:")


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p", "record_hash": "r"}
    b = {"x": 1, "previous_hash": "q", "record_hash": "s"}
    assert M.content_hash(a) == M.content_hash(b)


# ══════════════ 보안 스캔 ══════════════
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
    forbidden = ("def execute_trade", "def deploy", "def allocate", "def modify_permission",
                 "def execute", "def place_order", "def promote_live")
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
    import jarvis.research_agent_coordinator.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_rac_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("coord1", "agentA", "r", T[0], commit=True)
    e.assign_agent("coord1", "agentB", "r", T[0], commit=True)
    aid = e.create_task_assignment("coord1", "TASK1", "agentA", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    e.record_handoff(aid, "agentB", "EVID1", "", T[3], commit=True)
    e.resolve_assignment_conflict("TASK1", ["a"], "a", "", T[4], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("rac_"), fn


def test_no_rco_files_written(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    for fn in os.listdir(tmp_path):
        assert not fn.startswith("rco_"), fn


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
    from jarvis.research_agent_coordinator.__main__ import main
    assert main(["summary"]) == 0
    assert "ownership_event_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordinator.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordinator.__main__ import main
    main(["assign", "--coordinator", "c1", "--agent", "a1", "--commit"])
    capsys.readouterr()
    main(["task", "--coordinator", "c1", "--task", "T1", "--agent", "a1", "--commit"])
    aid = json.loads(capsys.readouterr().out)["assignment"]["assignment_id"]
    main(["progress", "--assignment", aid, "--percent", "50", "--commit"])
    capsys.readouterr()
    main(["review", "--assignment", aid, "--commit"])
    capsys.readouterr()
    assert main(["complete", "--assignment", aid, "--result", "R1", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == A_COMPLETED


def test_cli_handoff(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordinator.__main__ import main
    main(["assign", "--coordinator", "c1", "--agent", "a1", "--commit"])
    capsys.readouterr()
    main(["assign", "--coordinator", "c1", "--agent", "a2", "--commit"])
    capsys.readouterr()
    main(["task", "--coordinator", "c1", "--task", "T1", "--agent", "a1", "--commit"])
    aid = json.loads(capsys.readouterr().out)["assignment"]["assignment_id"]
    main(["progress", "--assignment", aid, "--percent", "40", "--commit"])
    capsys.readouterr()
    assert main(["handoff", "--assignment", aid, "--to", "a2", "--evidence", "EV1",
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["handoff"]["to_agent"] == "a2"


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordinator.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_report_and_assignments(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordinator.__main__ import main
    main(["assign", "--coordinator", "c1", "--agent", "a1", "--commit"])
    capsys.readouterr()
    main(["task", "--coordinator", "c1", "--task", "T1", "--agent", "a1", "--commit"])
    capsys.readouterr()
    assert main(["report", "--coordinator", "c1", "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["is_binding"] is False
    assert main(["assignments", "--coordinator", "c1"]) == 0
    assert len(json.loads(capsys.readouterr().out)["assignments"]) == 1


def test_cli_conflict(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordinator.__main__ import main
    assert main(["conflict", "--task", "T1", "--winning", "a1", "--agents", "a1,a2",
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["collaboration"]["winning_agent"] == "a1"


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("st", list(ASSIGNMENT_STATES))
def test_state_membership(st):
    assert st in ASSIGNMENT_STATES


@pytest.mark.parametrize("agent", ["a1", "a2", "a3", "a4", "a5"])
def test_multiple_agents(tmp_path, monkeypatch, agent):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.assign_agent("c1", agent, "r", T[0], commit=True)
    assert r.agent == agent


@pytest.mark.parametrize("task", ["T1", "T2", "T3", "T4"])
def test_multiple_tasks(tmp_path, monkeypatch, task):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("c1", "a1", "r", T[0], commit=True)
    a = e.create_task_assignment("c1", task, "a1", "", T[1], commit=True)
    assert a.task_ref == task


def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("c1", "a1", "r", T[0], commit=True)
    e.create_task_assignment("c1", "T1", "a1", "", T[1], commit=False)
    assert ledger.read_ownership_events() == []


def test_assignment_meta_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    m = e.assignment_meta(aid)
    assert m["task_ref"] == "TASK1" and m["agent"] == "agentA"


def test_coordinator_assignments_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("c1", "a1", "r", T[0], commit=True)
    e.assign_agent("c2", "a2", "r", T[0], commit=True)
    e.create_task_assignment("c1", "T1", "a1", "", T[1], commit=True)
    e.create_task_assignment("c2", "T2", "a2", "", T[2], commit=True)
    assert len(ledger.coordinator_assignments("c1")) == 1


def test_progress_result_ref_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    p = e.track_progress(aid, 90, "almost", "PARTIAL_RES", T[3], commit=True)
    assert p.result_ref == "PARTIAL_RES"


def test_review_from_handoff(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("c1", "a1", "r", T[0], commit=True)
    e.assign_agent("c1", "a2", "r", T[0], commit=True)
    aid = e.create_task_assignment("c1", "T1", "a1", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    e.record_handoff(aid, "a2", "EV1", "", T[3], commit=True)
    e.submit_for_review(aid, T[4], commit=True)
    assert e.current_state(aid) == A_REVIEW


@pytest.mark.parametrize("pct", [0, 10, 25, 50, 75, 100])
def test_progress_percentages(tmp_path, monkeypatch, pct):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e, task=f"T{pct}")
    p = e.track_progress(aid, pct, "", "", T[3], commit=True)
    assert p.percent == pct


@pytest.mark.parametrize("cap", ["data", "strategy", "review", "risk", "knowledge"])
def test_agent_capabilities(tmp_path, monkeypatch, cap):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.assign_agent("c1", f"agent_{cap}", cap, T[0], commit=True)
    assert r.capability == cap


def test_ownership_event_carries_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    aid = _assignment(e)
    for ev in ledger.assignment_events(aid):
        assert ev["task_ref"] == "TASK1"


def test_handoff_record_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("c1", "a1", "r", T[0], commit=True)
    e.assign_agent("c1", "a2", "r", T[0], commit=True)
    aid = e.create_task_assignment("c1", "T1", "a1", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 40, "", "", T[2], commit=True)
    h = e.record_handoff(aid, "a2", "EV1", "note", T[3], commit=True)
    assert h.from_agent == "a1" and h.to_agent == "a2" and h.evidence_ref == "EV1"


def test_collaboration_agents_sorted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = e.resolve_assignment_conflict("T1", ["z", "a", "m"], "a", "", T[5], commit=True)
    assert c.agents == ["a", "m", "z"]


def test_two_handoffs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for ag in ("a1", "a2", "a3"):
        e.assign_agent("c1", ag, "r", T[0], commit=True)
    aid = e.create_task_assignment("c1", "T1", "a1", "", T[1], commit=True).assignment_id
    e.track_progress(aid, 30, "", "", T[2], commit=True)
    e.record_handoff(aid, "a2", "EV1", "", T[3], commit=True)
    e.track_progress(aid, 60, "", "", T[4], commit=True)
    e.record_handoff(aid, "a3", "EV2", "", T[5], commit=True)
    assert len(ledger.assignment_handoffs(aid)) == 2
    assert e.current_owner(aid) == "a3"


def test_assign_agent_unknown_assignment_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownAssignmentError):
        e.assignment_meta("ACO:ghost")


def test_submit_for_review_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownAssignmentError):
        e.submit_for_review("ACO:ghost", T[3], commit=True)


def test_report_active_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    rep = e.generate_coordination_report("coord1", "ALL", T[10], commit=True)
    assert rep.active_count == 1


def test_report_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    rep = e.generate_coordination_report("coord1", "ALL", T[10], commit=True)
    assert rep.state_distribution.get(A_ASSIGNED) == 1


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []
    assert M.detect_cycle([("a", "b")]) == []


def test_current_owner_none_for_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    assert e.current_owner("ACO:ghost") is None


def test_verify_all_ledgers_in_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _assignment(e)
    res = verify_chain()
    for fn, _ in ledger.ALL_LEDGERS:
        assert fn in res["ledgers"]


@pytest.mark.parametrize("coord", ["c1", "c2", "c3"])
def test_multiple_coordinators(tmp_path, monkeypatch, coord):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent(coord, "a1", "r", T[0], commit=True)
    a = e.create_task_assignment(coord, "T1", "a1", "", T[1], commit=True)
    assert a.coordinator == coord


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_progress_id_varies_with_seq():
    assert M.progress_id("a", 0) != M.progress_id("a", 1)


def test_handoff_id_varies_with_seq():
    assert M.handoff_id("a", 0) != M.handoff_id("a", 1)


def test_end_to_end_coordination(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assign_agent("research_coord", "data_analyst", "data", T[0], commit=True)
    e.assign_agent("research_coord", "strategy_researcher", "strategy", T[0], commit=True)
    a1 = e.create_task_assignment("research_coord", "ingest_task", "data_analyst", "", T[1],
                                  commit=True).assignment_id
    e.track_progress(a1, 100, "done", "clean_data", T[2], commit=True)
    e.record_handoff(a1, "strategy_researcher", "clean_data_evidence", "", T[3], commit=True)
    e.track_progress(a1, 100, "strategy built", "strategy_v1", T[4], commit=True)
    e.submit_for_review(a1, T[5], commit=True)
    e.complete_assignment(a1, "final_strategy", T[6], commit=True)
    assert e.current_state(a1) == A_COMPLETED
    assert e.current_owner(a1) == "strategy_researcher"
    rep = e.generate_coordination_report("research_coord", "ALL", T[7], commit=True)
    assert rep.completed_count == 1
    assert rep.handoff_count == 1
    assert verify_chain()["ok"] is True
