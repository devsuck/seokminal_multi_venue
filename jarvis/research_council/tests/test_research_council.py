"""P11.6 Multi-Agent Research Council 테스트. **다중 AI 연구 에이전트 협의체 — 협의·기록 전용.**

협의체 등록(불변)·세션 생애주기(CREATED→ACTIVE→DISCUSSING→VOTING→CONSENSUS→CLOSED)·참가자 초대(8역할·불변)·
토론/논증/반대논증·투표(불변)·합의 계산(UNANIMOUS/MAJORITY/SPLIT/NO_CONSENSUS·결정적)·소수의견 보존·결정 요약
(is_decision=False)·협의체 리포트(is_binding=False)·아티팩트 계보·verify(체인/변조/중복/생애주기/합의결정성/소수보존/
계보)·replay·CLI·보안(금지import·실행/승인/배포 없음·삭제 API 없음·불변·COUNCIL≠EXECUTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_council import ledger
from jarvis.research_council import models as M
from jarvis.research_council.engine import ResearchCouncilEngine
from jarvis.research_council.models import (
    C_MAJORITY,
    C_NO_CONSENSUS,
    C_SPLIT,
    C_UNANIMOUS,
    ROLE_ALPHA,
    ROLE_DATA,
    ROLE_RISK,
    ROLE_STRATEGY,
    S_ACTIVE,
    S_CLOSED,
    S_CONSENSUS,
    S_CREATED,
    S_DISCUSSING,
    S_VOTING,
    STANCE_AGAINST,
    STANCE_FOR,
    IllegalSessionTransition,
    ImmutableArgumentError,
    ImmutableCouncilError,
    ImmutableParticipantError,
    ImmutableVoteError,
    InvalidAgentRole,
    InvalidVoteChoice,
    UnknownArgumentError,
    UnknownCouncilError,
    UnknownSessionError,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(30)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_council.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchCouncilEngine()


def _council(e, name="alpha_council", now=T[0]):
    return e.register_council(name, "coordinate research", now, commit=True).council_id


def _session(e, council=None, topic="promote strat X", now=T[0]):
    if council is None:
        council = _council(e, now=now)
    return e.create_session(council, topic, "decide research direction", now, commit=True).session_id


def _discussing(e):
    """DISCUSSING 상태 세션 + 3 참가자."""
    council = _council(e)
    s = e.create_session(council, "topic1", "obj", T[0], commit=True).session_id
    e.activate_session(s, T[1], commit=True)
    e.invite_agent(s, "data_agent", ROLE_DATA, T[1], commit=True)
    e.invite_agent(s, "strat_agent", ROLE_STRATEGY, T[1], commit=True)
    e.invite_agent(s, "risk_agent", ROLE_RISK, T[1], commit=True)
    e.start_discussion(s, T[2], commit=True)
    return council, s


# ══════════════ register_council ══════════════
def test_council_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().register_council("c1", "mandate", T[0], commit=True)
    assert c.council_id.startswith("CNL:")


def test_council_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_council("c", "m", T[0], commit=False)
    b = _eng().register_council("c", "m2", T[1], commit=False)
    assert a.council_id == b.council_id


def test_council_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _council(e)
    _council(e, now=T[1])
    assert len(ledger.read_councils()) == 1


def test_council_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _council(e)
    assert any(a["artifact_type"] == "COUNCIL" for a in ledger.read_artifacts())


# ══════════════ create_session / lifecycle ══════════════
def test_session_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    assert e.current_state(s) == S_CREATED


def test_session_unknown_council(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownCouncilError):
        _eng().create_session("CNL:ghost", "t", "", T[0], commit=True)


def test_session_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    e.activate_session(s, T[1], commit=True)
    assert e.current_state(s) == S_ACTIVE
    e.start_discussion(s, T[2], commit=True)
    assert e.current_state(s) == S_DISCUSSING
    e.open_voting(s, T[3], commit=True)
    assert e.current_state(s) == S_VOTING
    e.reach_consensus(s, T[4], commit=True)
    assert e.current_state(s) == S_CONSENSUS
    e.close_session(s, T[5], commit=True)
    assert e.current_state(s) == S_CLOSED


def test_session_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    with pytest.raises(IllegalSessionTransition):
        e.open_voting(s, T[1], commit=True)  # CREATED->VOTING 불가


def test_session_revote_loop(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    e.activate_session(s, T[1], commit=True)
    e.start_discussion(s, T[2], commit=True)
    e.open_voting(s, T[3], commit=True)
    e.start_discussion(s, T[4], commit=True)  # VOTING->DISCUSSING 재토론
    assert e.current_state(s) == S_DISCUSSING


def test_session_closed_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    e.activate_session(s, T[1], commit=True)
    e.close_session(s, T[2], commit=True)
    with pytest.raises(IllegalSessionTransition):
        e.start_discussion(s, T[3], commit=True)


def test_session_idempotent_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _council(e)
    e.create_session(c, "t", "o", T[0], commit=True)
    e.create_session(c, "t", "o", T[1], commit=True)
    assert len(ledger.session_ids()) == 1


def test_session_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _council(e)
    s = e.create_session(c, "TopicY", "ObjZ", T[0], commit=True).session_id
    m = e.session_meta(s)
    assert m["topic"] == "TopicY"
    assert m["council_id"] == c


def test_six_states():
    assert len(M.COUNCIL_STATES) == 6


# ══════════════ invite_agent ══════════════
def test_invite_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    p = e.invite_agent(s, "data_agent", ROLE_DATA, T[1], commit=True)
    assert p.participant_id.startswith("CNP:")
    assert p.role == ROLE_DATA


def test_invite_invalid_role(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    with pytest.raises(InvalidAgentRole):
        e.invite_agent(s, "x", "TRADER", T[1], commit=True)


@pytest.mark.parametrize("role", list(M.AGENT_ROLES))
def test_invite_all_eight_roles(tmp_path, monkeypatch, role):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    p = e.invite_agent(s, f"agent_{role}", role, T[1], commit=True)
    assert p.role == role


def test_invite_immutable_role_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    e.invite_agent(s, "a", ROLE_DATA, T[1], commit=True)
    with pytest.raises(ImmutableParticipantError):
        e.invite_agent(s, "a", ROLE_RISK, T[2], commit=True)


def test_invite_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    e.invite_agent(s, "a", ROLE_DATA, T[1], commit=True)
    e.invite_agent(s, "a", ROLE_DATA, T[2], commit=True)
    assert len(ledger.session_participants(s)) == 1


def test_eight_council_members():
    assert len(M.AGENT_ROLES) == 8


def test_participants_of(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    assert e.participants_of(s) == sorted(["data_agent", "strat_agent", "risk_agent"])


# ══════════════ discussion / arguments ══════════════
def test_submit_discussion(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    d = e.submit_discussion(s, "data_agent", "data is clean", T[3], commit=True)
    assert d.discussion_id.startswith("CND:")


def test_submit_argument(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    a = e.submit_argument(s, "strat_agent", "alpha is robust", STANCE_FOR, T[3], commit=True)
    assert a.argument_id.startswith("CNA:")
    assert a.stance == STANCE_FOR
    assert a.is_counter is False


def test_submit_counter_argument(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    a = e.submit_argument(s, "strat_agent", "alpha robust", STANCE_FOR, T[3], commit=True)
    c = e.submit_counter_argument(s, "risk_agent", a.argument_id, "overfit risk", T[4],
                                  commit=True)
    assert c.is_counter is True
    assert c.stance == STANCE_AGAINST  # 부모의 반대
    assert c.parent_argument == a.argument_id


def test_counter_unknown_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    with pytest.raises(UnknownArgumentError):
        e.submit_counter_argument(s, "risk_agent", "CNA:ghost", "x", T[3], commit=True)


def test_argument_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.submit_argument(s, "strat_agent", "same claim", STANCE_FOR, T[3], commit=True)
    with pytest.raises(ImmutableArgumentError):
        e.submit_argument(s, "strat_agent", "same claim", STANCE_AGAINST, T[4], commit=True)


def test_argument_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.submit_argument(s, "strat_agent", "c", STANCE_FOR, T[3], commit=True)
    assert any(a["artifact_type"] == "ARGUMENT" for a in ledger.read_artifacts())


# ══════════════ record_vote ══════════════
def test_record_vote(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.open_voting(s, T[3], commit=True)
    v = e.record_vote(s, "topic1", "data_agent", "FOR", "clean data", T[4], commit=True)
    assert v.vote_id.startswith("CNV:")
    assert v.choice == "FOR"


def test_vote_invalid_choice(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    with pytest.raises(InvalidVoteChoice):
        e.record_vote(s, "topic1", "data_agent", "MAYBE", "", T[3], commit=True)


def test_vote_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.record_vote(s, "topic1", "data_agent", "FOR", "", T[3], commit=True)
    with pytest.raises(ImmutableVoteError):
        e.record_vote(s, "topic1", "data_agent", "AGAINST", "", T[4], commit=True)


def test_vote_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.record_vote(s, "topic1", "data_agent", "FOR", "", T[3], commit=True)
    e.record_vote(s, "topic1", "data_agent", "FOR", "", T[4], commit=True)
    assert len(ledger.topic_votes(s, "topic1")) == 1


@pytest.mark.parametrize("choice", list(M.VOTE_CHOICES))
def test_vote_all_choices(tmp_path, monkeypatch, choice):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    v = e.record_vote(s, "topic1", "data_agent", choice, "", T[3], commit=True)
    assert v.choice == choice


# ══════════════ calculate_consensus (deterministic, 4 outcomes) ══════════════
def _vote_all(e, s, votes, topic="topic1", t0=3):
    for i, (agent, choice) in enumerate(votes):
        e.record_vote(s, topic, agent, choice, "", T[t0 + i], commit=True)


def test_consensus_unanimous(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR"), ("risk_agent", "FOR")])
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    assert c.outcome == C_UNANIMOUS
    assert c.winning_stance == STANCE_FOR


def test_consensus_majority(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR"), ("risk_agent", "AGAINST")])
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    assert c.outcome == C_MAJORITY
    assert c.winning_stance == STANCE_FOR


def test_consensus_split(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "AGAINST")])
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    assert c.outcome == C_SPLIT
    assert c.winning_stance == ""


def test_consensus_no_consensus(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "ABSTAIN"), ("strat_agent", "ABSTAIN")])
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    assert c.outcome == C_NO_CONSENSUS


def test_consensus_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    assert c.outcome == C_NO_CONSENSUS
    assert c.participant_count == 0


def test_consensus_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "AGAINST"), ("risk_agent", "FOR")])
    a = e.calculate_consensus(s, "topic1", T[10], commit=False)
    b = e.calculate_consensus(s, "topic1", T[11], commit=False)
    assert a.outcome == b.outcome
    assert a.consensus_id == b.consensus_id


def test_consensus_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    e.record_vote(s, "topic1", "risk_agent", "AGAINST", "", T[11], commit=True)
    with pytest.raises(Exception):  # ImmutableConsensusError
        e.calculate_consensus(s, "topic1", T[10], commit=True)


def test_consensus_tally(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR"), ("risk_agent", "AGAINST")])
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    assert c.for_count == 2
    assert c.against_count == 1


def test_four_outcomes():
    assert len(M.CONSENSUS_OUTCOMES) == 4


# ══════════════ pure consensus functions ══════════════
def test_consensus_outcome_pure():
    assert M.consensus_outcome(["FOR", "FOR"]) == C_UNANIMOUS
    assert M.consensus_outcome(["FOR", "FOR", "AGAINST"]) == C_MAJORITY
    assert M.consensus_outcome(["FOR", "AGAINST"]) == C_SPLIT
    assert M.consensus_outcome(["ABSTAIN"]) == C_NO_CONSENSUS
    assert M.consensus_outcome([]) == C_NO_CONSENSUS


def test_winning_stance_pure():
    assert M.winning_stance(["FOR", "FOR", "AGAINST"]) == STANCE_FOR
    assert M.winning_stance(["AGAINST", "AGAINST", "FOR"]) == STANCE_AGAINST
    assert M.winning_stance(["FOR", "AGAINST"]) == ""


def test_tally_votes_pure():
    assert M.tally_votes(["FOR", "FOR", "AGAINST", "ABSTAIN"]) == {"FOR": 2, "AGAINST": 1,
                                                                   "ABSTAIN": 1}


# ══════════════ minority preservation ══════════════
def test_record_minority(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR"), ("risk_agent", "AGAINST")])
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    m = e.record_minority(s, c.consensus_id, "risk_agent", STANCE_AGAINST, "overfit", T[11],
                          commit=True)
    assert m.minority_id.startswith("CNM:")


def test_preserve_minority(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR"), ("risk_agent", "AGAINST")])
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    ms = e.preserve_minority(s, "topic1", T[11], commit=True)
    assert len(ms) == 1  # risk_agent 는 소수(패배)
    assert ms[0].participant == "risk_agent"


def test_preserve_minority_none_when_unanimous(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    assert e.preserve_minority(s, "topic1", T[11], commit=True) == []


def test_minority_preserved_verify(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_council.verify import minority_preservation
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR"), ("risk_agent", "AGAINST")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    assert minority_preservation()["ok"] is False  # 아직 미보존
    e.preserve_minority(s, "topic1", T[11], commit=True)
    assert minority_preservation()["ok"] is True


# ══════════════ generate_summary (is_decision=False) ══════════════
def test_summary_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    su = e.generate_summary(s, "topic1", "recommend further research", T[11], commit=True)
    assert su.summary_id.startswith("CNU:")
    assert su.is_decision is False
    assert su.outcome == C_UNANIMOUS


def test_summary_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    su = e.generate_summary(s, "topic1", "", T[11], commit=True)
    assert "CONSENSUS ≠ APPROVAL" in su.disclaimer


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    a = e.generate_summary(s, "topic1", "r", T[11], commit=False)
    b = e.generate_summary(s, "topic1", "r", T[11], commit=False)
    assert a.to_dict() == b.to_dict()


def test_summary_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.generate_summary(s, "topic1", "r", T[11], commit=True)
    e.generate_summary(s, "topic1", "r", T[12], commit=True)
    assert len(ledger.read_summaries()) == 1


# ══════════════ generate_report (is_binding=False) ══════════════
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    council, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    r = e.generate_report(council, "COUNCIL", T[12], commit=True)
    assert r.report_id.startswith("CNR:")
    assert r.is_binding is False
    assert r.consensus_count == 1


def test_report_outcome_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    council, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    r = e.generate_report(council, "COUNCIL", T[12], commit=True)
    assert r.outcome_distribution[C_UNANIMOUS] == 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    council = _council(e)
    a = e.generate_report(council, "COUNCIL", T[5], commit=False)
    b = e.generate_report(council, "COUNCIL", T[5], commit=False)
    assert a.to_dict() == b.to_dict()


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_council.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_full_council(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_council.verify import verify_chain
    e = _eng()
    council, s = _discussing(e)
    a = e.submit_argument(s, "strat_agent", "robust", STANCE_FOR, T[3], commit=True)
    e.submit_counter_argument(s, "risk_agent", a.argument_id, "overfit", T[4], commit=True)
    e.open_voting(s, T[5], commit=True)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR"), ("risk_agent", "AGAINST")],
              t0=6)
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    e.preserve_minority(s, "topic1", T[11], commit=True)
    e.reach_consensus(s, T[12], commit=True)
    e.generate_summary(s, "topic1", "recommend", T[13], commit=True)
    e.generate_report(council, "COUNCIL", T[14], commit=True)
    res = verify_chain(check_minority=True)
    assert res["ok"] is True
    assert res["lifecycle"]["ok"]
    assert res["determinism"]["ok"]
    assert res["lineage"]["ok"]
    assert res["minority"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _council(e)
    p = sp("cnl_councils.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_council.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_verify_determinism_detects_forged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    p = sp("cnl_consensus.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["outcome"] = "MAJORITY"
    rows[0]["record_hash"] = M.content_hash(rows[0])
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_council.verify import consensus_determinism
    assert consensus_determinism()["ok"] is False


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_council.verify import replay
    e = _eng()
    _discussing(e)
    assert replay(e, T[5])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    council, s = _discussing(e)
    e.submit_argument(s, "strat_agent", "c", STANCE_FOR, T[3], commit=True)
    _vote_all(e, s, [("data_agent", "FOR")], t0=4)
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    su = e.summary(T[12])
    assert su.council_count == 1
    assert su.argument_count == 1
    assert su.vote_count == 1
    assert su.consensus_count == 1


# ══════════════ 보안 / 불변식 (no execution capability) ══════════════
def test_no_forbidden_imports():
    import ast
    forbidden_prefixes = ("execution", "broker", "portfolio", "risk", "permission", "live",
                          "deployment", "order", "capital_allocation", "live_trading",
                          "risk_controller", "portfolio_execution")
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
                    assert not (sub == fb or sub.startswith(fb + ".") or sub.startswith(fb)), (fn, m)


def test_engine_no_execution_methods():
    e = ResearchCouncilEngine()
    for bad in ("approve_strategy", "deploy", "deploy_strategy", "trade", "allocate",
                "allocate_capital", "modify_permission", "change_config", "execute",
                "execute_order", "call_broker", "modify_portfolio", "approve", "activate"):
        assert not hasattr(e, bad), bad


def test_no_execution_verbs_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def approve_strategy", "def deploy", "def trade", "def allocate",
                    "def execute", "def call_broker", "def modify_portfolio",
                    "def modify_permission", "def change_config"):
            assert bad not in src, (fn, bad)


def test_forbidden_verbs_defined():
    for v in ("APPROVE_STRATEGY", "DEPLOY", "TRADE", "ALLOCATE_CAPITAL", "EXECUTE_ORDER",
              "CALL_BROKER", "MODIFY_PORTFOLIO"):
        assert M.is_forbidden_verb(v) is True
    assert M.is_forbidden_verb("DISCUSS") is False


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
    from jarvis.research_council.engine import _DISCLAIMER
    assert "COUNCIL ≠ EXECUTION" in _DISCLAIMER
    assert "CONSENSUS ≠ APPROVAL" in _DISCLAIMER


def test_all_summaries_not_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.generate_summary(s, "topic1", "r", T[11], commit=True)
    for r in ledger.read_summaries():
        assert r["is_decision"] is False


def test_all_reports_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    council = _council(e)
    e.generate_report(council, "COUNCIL", T[5], commit=True)
    for r in ledger.read_reports():
        assert r["is_binding"] is False


def test_records_frozen():
    c = M.ConsensusRecord(consensus_id="CNC:x", session_id="CNS:s", topic="t", outcome="UNANIMOUS",
                          for_count=1, against_count=0, abstain_count=0, winning_stance="FOR",
                          participant_count=1, created_at=T[0])
    with pytest.raises(Exception):
        c.outcome = "SPLIT"  # type: ignore


def test_only_cnl_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    council, s = _discussing(e)
    e.submit_argument(s, "strat_agent", "c", STANCE_FOR, T[3], commit=True)
    e.open_voting(s, T[5], commit=True)
    _vote_all(e, s, [("data_agent", "FOR")], t0=6)
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    e.generate_summary(s, "topic1", "r", T[11], commit=True)
    e.generate_report(council, "COUNCIL", T[12], commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("cnl_"), fn


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.council_id("n")[:4], M.session_id("c", "t")[:4], M.session_event_id("s", "x")[:4],
           M.participant_id("s", "a")[:4], M.discussion_id("s", "p", "m")[:4],
           M.argument_id("s", "p", "c")[:4], M.vote_id("s", "t", "p")[:4],
           M.consensus_id("s", "t")[:4], M.minority_id("s", "c", "p")[:4],
           M.summary_id("s", "t")[:4], M.report_id("c", "s", T[0])[:4],
           M.artifact_id("t", "r")[:4]}
    assert len(ids) == 12


def test_eleven_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 11
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 11
    assert all(f.startswith("cnl_") for f in fns)


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b")]) == []
    cyc = M.detect_cycle([("a", "b"), ("b", "a")])
    assert cyc and cyc[0] == cyc[-1]


def test_list_sessions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    council, s = _discussing(e)
    assert s in e.list_sessions(council)


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_council.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_council_session_invite(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["council", "--name", "c1", "--commit"], capsys)
    assert rc == 0
    cid = json.loads(out)["council"]["council_id"]
    rc2, out2 = _run(["session", "--council", cid, "--topic", "t1", "--commit"], capsys)
    assert rc2 == 0
    sid = json.loads(out2)["session"]["session_id"]
    _run(["advance", "--session", sid, "--to", "ACTIVE", "--commit"], capsys)
    rc3, out3 = _run(["invite", "--session", sid, "--agent", "a1", "--role", "DATA", "--commit"],
                     capsys)
    assert rc3 == 0
    assert json.loads(out3)["participant"]["role"] == "DATA"


def test_cli_argue_and_vote_and_consensus(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    council, s = _discussing(e)
    rc, out = _run(["argue", "--session", s, "--agent", "strat_agent", "--claim", "robust",
                    "--commit"], capsys)
    assert rc == 0
    _run(["advance", "--session", s, "--to", "VOTING", "--commit"], capsys)
    _run(["vote", "--session", s, "--topic", "topic1", "--agent", "data_agent",
          "--choice", "FOR", "--commit"], capsys)
    _run(["vote", "--session", s, "--topic", "topic1", "--agent", "strat_agent",
          "--choice", "FOR", "--commit"], capsys)
    rc2, out2 = _run(["consensus", "--session", s, "--topic", "topic1", "--commit"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["consensus"]["outcome"] == "UNANIMOUS"


def test_cli_counter(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    a = e.submit_argument(s, "strat_agent", "robust", STANCE_FOR, T[3], commit=True)
    rc, out = _run(["counter", "--session", s, "--agent", "risk_agent", "--parent",
                    a.argument_id, "--claim", "overfit", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["argument"]["is_counter"] is True


def test_cli_minority_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR"), ("risk_agent", "AGAINST")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    rc, out = _run(["minority", "--session", s, "--topic", "topic1", "--commit"], capsys)
    assert rc == 0
    assert len(json.loads(out)["minority"]) == 1
    rc2, out2 = _run(["summary-of", "--session", s, "--topic", "topic1", "--commit"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["summary"]["is_decision"] is False


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    council = _council(e)
    rc, out = _run(["report", "--council", council, "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _discussing(_eng())
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "council_count" in json.loads(out)


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (S_CREATED, S_ACTIVE, True), (S_ACTIVE, S_DISCUSSING, True), (S_ACTIVE, S_CLOSED, True),
    (S_DISCUSSING, S_VOTING, True), (S_DISCUSSING, S_ACTIVE, True), (S_VOTING, S_CONSENSUS, True),
    (S_VOTING, S_DISCUSSING, True), (S_CONSENSUS, S_CLOSED, True),
    (S_CREATED, S_VOTING, False), (S_CREATED, S_CLOSED, False), (S_CLOSED, S_ACTIVE, False),
    (S_CONSENSUS, S_ACTIVE, False),
])
def test_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


@pytest.mark.parametrize("choices,outcome", [
    (["FOR", "FOR", "FOR"], C_UNANIMOUS),
    (["AGAINST", "AGAINST"], C_UNANIMOUS),
    (["FOR", "FOR", "AGAINST"], C_MAJORITY),
    (["AGAINST", "AGAINST", "AGAINST", "FOR"], C_MAJORITY),
    (["FOR", "AGAINST"], C_SPLIT),
    (["FOR", "FOR", "AGAINST", "AGAINST"], C_SPLIT),
    (["ABSTAIN", "ABSTAIN"], C_NO_CONSENSUS),
    ([], C_NO_CONSENSUS),
    (["FOR", "ABSTAIN"], C_UNANIMOUS),
])
def test_consensus_outcome_matrix(choices, outcome):
    assert M.consensus_outcome(choices) == outcome


def test_council_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_council("c", "m", T[0], commit=False)
    assert ledger.read_councils() == []


def test_session_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _council(e)
    e.create_session(c, "t", "o", T[0], commit=False)
    assert ledger.read_session_events() == []


def test_invite_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = _session(e)
    e.invite_agent(s, "a", ROLE_DATA, T[1], commit=False)
    assert ledger.read_participants() == []


def test_argument_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.submit_argument(s, "strat_agent", "c", STANCE_FOR, T[3], commit=False)
    assert ledger.read_arguments() == []


def test_vote_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.record_vote(s, "topic1", "data_agent", "FOR", "", T[3], commit=False)
    assert ledger.read_votes() == []


def test_invite_unknown_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSessionError):
        _eng().invite_agent("CNS:ghost", "a", ROLE_DATA, T[0], commit=True)


def test_argue_unknown_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSessionError):
        _eng().submit_argument("CNS:ghost", "a", "c", STANCE_FOR, T[0], commit=True)


def test_vote_unknown_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSessionError):
        _eng().record_vote("CNS:ghost", "t", "a", "FOR", "", T[0], commit=True)


def test_session_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSessionError):
        _eng().session_meta("CNS:ghost")


def test_multiple_sessions_one_council(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _council(e)
    s1 = e.create_session(c, "t1", "o", T[0], commit=True).session_id
    s2 = e.create_session(c, "t2", "o", T[0], commit=True).session_id
    assert sorted(e.list_sessions(c)) == sorted([s1, s2])


def test_arguments_of(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    a = e.submit_argument(s, "strat_agent", "c", STANCE_FOR, T[3], commit=True)
    assert a.argument_id in e.arguments_of(s)


def test_minority_of(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("strat_agent", "FOR"), ("risk_agent", "AGAINST")])
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    e.preserve_minority(s, "topic1", T[11], commit=True)
    assert len(e.minority_of(c.consensus_id)) == 1


def test_discussion_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    e.submit_discussion(s, "data_agent", "msg", T[3], commit=True)
    e.submit_discussion(s, "data_agent", "msg", T[4], commit=True)
    assert len(ledger.session_discussions(s)) == 1


def test_counter_stance_flips_from_against(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    a = e.submit_argument(s, "risk_agent", "risky", STANCE_AGAINST, T[3], commit=True)
    c = e.submit_counter_argument(s, "strat_agent", a.argument_id, "actually fine", T[4],
                                  commit=True)
    assert c.stance == STANCE_FOR


def test_consensus_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    assert any(a["artifact_type"] == "CONSENSUS" for a in ledger.read_artifacts())


def test_summary_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR")])
    e.calculate_consensus(s, "topic1", T[10], commit=True)
    e.generate_summary(s, "topic1", "r", T[11], commit=True)
    assert any(a["artifact_type"] == "SUMMARY" for a in ledger.read_artifacts())


def test_lineage_verify_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_council.verify import lineage_integrity
    e = _eng()
    _, s = _discussing(e)
    e.submit_argument(s, "strat_agent", "c", STANCE_FOR, T[3], commit=True)
    assert lineage_integrity()["ok"] is True


def test_minority_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _, s = _discussing(e)
    _vote_all(e, s, [("data_agent", "FOR"), ("risk_agent", "AGAINST")])
    c = e.calculate_consensus(s, "topic1", T[10], commit=True)
    e.record_minority(s, c.consensus_id, "risk_agent", STANCE_AGAINST, "op1", T[11], commit=True)
    with pytest.raises(Exception):  # ImmutableMinorityError
        e.record_minority(s, c.consensus_id, "risk_agent", STANCE_AGAINST, "op2", T[12],
                          commit=True)


def test_report_multiple_sessions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _council(e)
    for i, topic in enumerate(["ta", "tb"]):
        s = e.create_session(c, topic, "o", T[0], commit=True).session_id
        e.activate_session(s, T[1], commit=True)
        e.invite_agent(s, "d", ROLE_DATA, T[1], commit=True)
        e.start_discussion(s, T[2], commit=True)
        e.open_voting(s, T[3], commit=True)
        e.record_vote(s, topic, "d", "FOR", "", T[4], commit=True)
        e.calculate_consensus(s, topic, T[5], commit=True)
    r = e.generate_report(c, "COUNCIL", T[6], commit=True)
    assert r.session_count == 2
    assert r.consensus_count == 2


def test_stances_and_choices_constants():
    assert set(M.STANCES) == {"FOR", "AGAINST"}
    assert set(M.VOTE_CHOICES) == {"FOR", "AGAINST", "ABSTAIN"}


# ══════════════ 통합 시나리오 (multi-agent discussion) ══════════════
def test_end_to_end_council(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    council = e.register_council("promotion_council", "review strategy promotions", T[0],
                                 commit=True).council_id
    s = e.create_session(council, "promote momentum_v2", "decide research go-ahead", T[0],
                         commit=True).session_id
    e.activate_session(s, T[1], commit=True)
    # 8종 에이전트 초대
    roster = [("data_agent", "DATA"), ("strat_agent", "STRATEGY"), ("alpha_agent", "ALPHA"),
              ("pf_agent", "PORTFOLIO"), ("risk_agent", "RISK"), ("sim_agent", "SIMULATION"),
              ("rev_agent", "REVIEWER"), ("kn_agent", "KNOWLEDGE")]
    for name, role in roster:
        e.invite_agent(s, name, role, T[1], commit=True)
    assert len(e.participants_of(s)) == 8
    e.start_discussion(s, T[2], commit=True)
    a = e.submit_argument(s, "alpha_agent", "momentum v2 has robust IR", STANCE_FOR, T[3],
                          commit=True)
    e.submit_counter_argument(s, "risk_agent", a.argument_id, "tail risk underestimated", T[4],
                              commit=True)
    e.submit_discussion(s, "rev_agent", "reproducibility acceptable", T[5], commit=True)
    e.open_voting(s, T[6], commit=True)
    # 6 FOR, 2 AGAINST -> MAJORITY
    votes = [(n, "FOR") for n, _ in roster[:6]] + [(n, "AGAINST") for n, _ in roster[6:]]
    _vote_all(e, s, votes, t0=7)
    cons = e.calculate_consensus(s, "topic1", T[20], commit=True)
    assert cons.outcome == C_MAJORITY
    assert cons.winning_stance == STANCE_FOR
    # 소수(패배 AGAINST) 2명 보존
    ms = e.preserve_minority(s, "topic1", T[21], commit=True)
    assert len(ms) == 2
    e.reach_consensus(s, T[22], commit=True)
    su = e.generate_summary(s, "topic1", "recommend research continuation (NOT deployment)", T[23],
                            commit=True)
    assert su.is_decision is False
    e.close_session(s, T[24], commit=True)
    rep = e.generate_report(council, "COUNCIL", T[25], commit=True)
    assert rep.is_binding is False
    assert rep.consensus_count == 1
    from jarvis.research_council.verify import verify_chain
    v = verify_chain(check_minority=True)
    assert v["ok"] is True
    assert v["minority"]["ok"] and v["determinism"]["ok"] and v["lineage"]["ok"]
