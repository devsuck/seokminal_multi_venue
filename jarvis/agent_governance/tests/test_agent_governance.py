"""P10.6 Agent Research Governance 테스트. **연구 에이전트 관리·감사 전용.**

에이전트 레지스트리(불변 정체성)·생명주기(REGISTERED→ACTIVE→SUSPENDED→RETIRED, 차단전이)·
능력(금지 능력 거부)·연구요청(CREATED→...→COMPLETED/REJECTED)·실험제안(DRAFT→...→ACCEPTED/
REJECTED)·행동감사(금지 행동 BLOCKED)·사람검토(자동 승인 금지)·연구예산(초과 BLOCKED)·계보·
verify(체인/변조/중복/계보/안전)·replay·CLI·보안(금지import·집행/브로커/주문/자본배분/배포/권한변경
없음·상위 원장 무변경·삭제 API 없음·불변·사람 승인 필수·Agent VALIDATED≠APPROVED FOR TRADING·
Proposal ACCEPTED≠EXECUTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.agent_governance import ledger
from jarvis.agent_governance import models as M
from jarvis.agent_governance.engine import AgentGovernanceEngine
from jarvis.agent_governance.models import (
    ACCEPTED,
    ACTIVE,
    APPROVE,
    APPROVED,
    COMPLETED,
    CREATED,
    DRAFT,
    REGISTERED,
    REJECT,
    REJECTED,
    REQUEST_CHANGE,
    RETIRED,
    REVIEWED,
    REVIEWING,
    RUNNING,
    SUBMITTED,
    SUSPENDED,
    ForbiddenCapability,
    HumanApprovalRequired,
    IllegalTransition,
    ImmutableAgentError,
    ImmutableRequestError,
    UnknownProposal,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.agent_governance.ledger.state_path", sp)
    return sp


def _eng():
    return AgentGovernanceEngine()


def _agent(eng, aid="AG1", caps=None, commit=True):
    return eng.register_agent(aid, f"{aid} researcher", "1.0", "anthropic",
                              caps or [M.READ_DATA], T0, commit=commit)


def _req(eng, aid="AG1", obj="find alpha", commit=True):
    return eng.create_request(aid, obj, ["dg_datasets:DS1"], T0, commit=commit)


def _prop(eng, rid, hyp="momentum works", commit=True):
    return eng.create_proposal(rid, hyp, "backtest", "sharpe>1", "low", T0, commit=commit)


# ── Agent Registry ──
def test_register_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _agent(eng)
    assert a.status == REGISTERED and a.provider == "anthropic"
    assert eng.agent_state("AG1") == REGISTERED


def test_agent_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _agent(_eng(), commit=True)
    assert len(ledger.read_agent_events()) == 1


def test_agent_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _agent(_eng(), commit=False)
    assert ledger.read_agent_events() == []


def test_agent_immutable_identity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    with pytest.raises(ImmutableAgentError):
        eng.register_agent("AG1", "different name", "1.0", "anthropic", [M.READ_DATA], T0,
                           commit=True)


def test_agent_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    _agent(eng)
    assert len(ledger.distinct_agents()) == 1


def test_agent_activate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.activate_agent("AG1", T1, commit=True)
    assert eng.agent_state("AG1") == ACTIVE


def test_agent_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.activate_agent("AG1", T1, commit=True)
    eng.transition_agent("AG1", SUSPENDED, T1, commit=True)
    eng.transition_agent("AG1", ACTIVE, T2, commit=True)
    eng.transition_agent("AG1", RETIRED, T2, commit=True)
    assert eng.agent_state("AG1") == RETIRED


def test_agent_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_agent("AG1", SUSPENDED, T1, commit=True)  # REGISTERED→SUSPENDED 차단


def test_agent_retired_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.transition_agent("AG1", RETIRED, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_agent("AG1", ACTIVE, T2, commit=True)


def test_agent_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(IllegalTransition):
        _eng().transition_agent("GHOST", ACTIVE, T1, commit=True)


def test_agent_transition_table():
    assert M.can_transition_agent("", REGISTERED)
    assert M.can_transition_agent(REGISTERED, ACTIVE)
    assert M.can_transition_agent(ACTIVE, SUSPENDED)
    assert M.can_transition_agent(SUSPENDED, ACTIVE)
    assert not M.can_transition_agent(REGISTERED, SUSPENDED)
    assert not M.can_transition_agent(RETIRED, ACTIVE)


def test_agent_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    assert any(a["artifact_type"] == M.ART_AGENT and a["ref_id"] == "AG1"
               for a in ledger.read_artifacts())


# ── Capability Registry ──
@pytest.mark.parametrize("cap", list(M.ALLOWED_CAPABILITIES))
def test_grant_allowed_capability(tmp_path, monkeypatch, cap):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    c = eng.grant_capability("AG1", cap, T0, commit=True)
    assert c.allowed is True and c.capability == cap


@pytest.mark.parametrize("cap", list(M.FORBIDDEN_CAPABILITIES))
def test_grant_forbidden_capability_rejected(tmp_path, monkeypatch, cap):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    with pytest.raises(ForbiddenCapability):
        eng.grant_capability("AG1", cap, T0, commit=True)


def test_grant_unknown_capability_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    with pytest.raises(ForbiddenCapability):
        eng.grant_capability("AG1", "MINT_MONEY", T0, commit=True)


def test_capability_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.grant_capability("AG1", M.READ_DATA, T0, commit=True)
    eng.grant_capability("AG1", M.READ_DATA, T0, commit=True)
    assert len(ledger.read_capabilities()) == 1


def test_agent_capabilities_list(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.grant_capability("AG1", M.READ_DATA, T0, commit=True)
    eng.grant_capability("AG1", M.GENERATE_REPORT, T0, commit=True)
    assert eng.agent_capabilities("AG1") == sorted([M.READ_DATA, M.GENERATE_REPORT])


def test_forbidden_capabilities_are_execution_related():
    assert set(M.FORBIDDEN_CAPABILITIES) == {
        "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "CHANGE_PERMISSION"}


# ── Research Request ──
def test_create_request(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    assert r.status == CREATED and r.agent_id == "AG1"
    assert eng.request_state(r.request_id) == CREATED


def test_request_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    rid = r.request_id
    eng.transition_request(rid, REVIEWING, T1, commit=True)
    eng.transition_request(rid, APPROVED, T1, commit=True)
    eng.transition_request(rid, RUNNING, T2, commit=True)
    eng.transition_request(rid, COMPLETED, T2, commit=True)
    assert eng.request_state(rid) == COMPLETED


def test_request_rejected_path(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    eng.transition_request(r.request_id, REVIEWING, T1, commit=True)
    eng.transition_request(r.request_id, REJECTED, T1, commit=True)
    assert eng.request_state(r.request_id) == REJECTED


def test_request_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_request(r.request_id, RUNNING, T1, commit=True)  # CREATED→RUNNING 차단


def test_request_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.create_request("AG1", "obj", ["a"], T0, commit=True)
    with pytest.raises(ImmutableRequestError):
        eng.create_request("AG1", "obj", ["b", "c"], T0, commit=True)


def test_request_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    _req(eng)
    _req(eng)
    assert len(ledger.distinct_requests()) == 1


def test_request_artifact_parent_is_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    ra = arts[M.artifact_id(M.ART_REQUEST, r.request_id)]
    assert ra["parent_artifact"] == M.artifact_id(M.ART_AGENT, "AG1")
    assert ra["parent_artifact"] in arts


# ── Experiment Proposal ──
def test_create_proposal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    assert p.status == DRAFT and p.request_id == r.request_id


def test_submit_proposal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    assert eng.proposal_state(p.proposal_id) == SUBMITTED


def test_proposal_transition_table():
    assert M.can_transition_proposal("", DRAFT)
    assert M.can_transition_proposal(DRAFT, SUBMITTED)
    assert M.can_transition_proposal(SUBMITTED, REVIEWED)
    assert M.can_transition_proposal(REVIEWED, ACCEPTED)
    assert not M.can_transition_proposal(DRAFT, ACCEPTED)
    assert not M.can_transition_proposal(ACCEPTED, REJECTED)


def test_proposal_submit_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownProposal):
        _eng().submit_proposal("GHOST", T1, commit=True)


def test_proposal_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    _prop(eng, r.request_id)
    _prop(eng, r.request_id)
    assert len(ledger.distinct_proposals()) == 1


def test_proposal_artifact_parent_is_request(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    pa = arts[M.artifact_id(M.ART_PROPOSAL, p.proposal_id)]
    assert pa["parent_artifact"] == M.artifact_id(M.ART_REQUEST, r.request_id)
    assert pa["parent_artifact"] in arts


# ── Human Review Workflow ──
def test_review_approve_accepts_proposal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    eng.record_review(p.proposal_id, "human_operator", APPROVE, "looks good", T2, commit=True)
    assert eng.proposal_state(p.proposal_id) == ACCEPTED


def test_review_reject(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    eng.record_review(p.proposal_id, "human_operator", REJECT, "flawed", T2, commit=True)
    assert eng.proposal_state(p.proposal_id) == REJECTED


def test_review_request_change_stays_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    eng.record_review(p.proposal_id, "human_operator", REQUEST_CHANGE, "revise", T2, commit=True)
    assert eng.proposal_state(p.proposal_id) == REVIEWED


def test_review_requires_human_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    with pytest.raises(HumanApprovalRequired):
        eng.record_review(p.proposal_id, "", APPROVE, "", T2, commit=True)


def test_review_whitespace_reviewer_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    with pytest.raises(HumanApprovalRequired):
        eng.record_review(p.proposal_id, "   ", APPROVE, "", T2, commit=True)


def test_review_missing_proposal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownProposal):
        _eng().record_review("GHOST", "human", APPROVE, "", T2, commit=True)


def test_no_auto_accept_api(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(HumanApprovalRequired):
        eng.accept_proposal("anything")


def test_review_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    eng.record_review(p.proposal_id, "human", APPROVE, "", T2, commit=True)
    assert len(ledger.read_reviews()) == 1
    assert ledger.reviews_for(p.proposal_id)[0]["reviewer"] == "human"


def test_review_draft_proposal_no_state_move(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)  # DRAFT, not submitted
    eng.record_review(p.proposal_id, "human", APPROVE, "", T2, commit=True)
    assert eng.proposal_state(p.proposal_id) == DRAFT  # 미제출 → 이동 없음


# ── Agent Action Audit ──
def test_record_allowed_action(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    a = eng.record_action("AG1", "CREATE_HYPOTHESIS", "H1", "ok", T0, commit=True)
    assert a.is_forbidden is False and a.result == "ok"


@pytest.mark.parametrize("act", list(M.FORBIDDEN_ACTIONS))
def test_record_forbidden_action_blocked(tmp_path, monkeypatch, act):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    a = eng.record_action("AG1", act, "target", "should_be_ignored", T0, commit=True)
    assert a.is_forbidden is True
    assert a.result == M.ACTION_BLOCKED


def test_forbidden_action_never_executes(tmp_path, monkeypatch):
    """금지 행동을 기록해도 result 는 항상 BLOCKED — 실제 실행 결과가 남지 않는다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    a = eng.record_action("AG1", "EXECUTE_TRADE", "AAPL", "filled", T0, commit=True)
    assert a.result == M.ACTION_BLOCKED and a.result != "filled"


def test_action_persisted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.record_action("AG1", "QUERY_KNOWLEDGE_GRAPH", "kg:1", "ok", T0, commit=True)
    assert len(ledger.read_actions()) == 1


def test_action_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.record_action("AG1", "GENERATE_REPORT", "R1", "ok", T0, commit=True)
    eng.record_action("AG1", "GENERATE_REPORT", "R1", "ok", T0, commit=True)
    assert len(ledger.read_actions()) == 1


# ── Research Budget Tracking ──
def test_set_budget(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    b = eng.set_budget("AG1", "2026Q3", 3, 100, T0, commit=True)
    assert b.record_type == M.BUDGET_LIMIT and b.max_experiments == 3
    st = eng.budget_status("AG1", "2026Q3")
    assert st["max_experiments"] == 3 and st["used_experiments"] == 0


def test_consume_budget_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.set_budget("AG1", "2026Q3", 2, 10, T0, commit=True)
    eng.consume_budget("AG1", "2026Q3", M.KIND_EXPERIMENT, T1, commit=True)
    st = eng.budget_status("AG1", "2026Q3")
    assert st["used_experiments"] == 1


def test_consume_budget_blocked_over_limit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.set_budget("AG1", "2026Q3", 1, 10, T0, commit=True)
    eng.consume_budget("AG1", "2026Q3", M.KIND_EXPERIMENT, T1, commit=True)
    over = eng.consume_budget("AG1", "2026Q3", M.KIND_EXPERIMENT, T2, commit=True)
    assert over.status == M.BUDGET_BLOCKED and over.amount == 0
    st = eng.budget_status("AG1", "2026Q3")
    assert st["used_experiments"] == 1  # blocked not counted


def test_consume_budget_no_limit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    b = eng.consume_budget("AG1", "2026Q3", M.KIND_QUERY, T1, commit=True)
    assert b.status == M.BUDGET_OK  # 한도 없으면 차단 안 함


def test_budget_queries_and_experiments_separate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.set_budget("AG1", "P", 1, 1, T0, commit=True)
    eng.consume_budget("AG1", "P", M.KIND_EXPERIMENT, T1, commit=True)
    q = eng.consume_budget("AG1", "P", M.KIND_QUERY, T1, commit=True)
    assert q.status == M.BUDGET_OK  # query 예산 별도


def test_budget_blocked_is_metadata_only(tmp_path, monkeypatch):
    """BLOCKED 는 연구 메타데이터 — 실제 실행 차단이 아니라 기록일 뿐."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.set_budget("AG1", "P", 0, 0, T0, commit=True)
    b = eng.consume_budget("AG1", "P", M.KIND_EXPERIMENT, T1, commit=True)
    assert b.status == M.BUDGET_BLOCKED
    # 기록은 남지만 어떤 실행도 일어나지 않는다(엔진에 실행 경로 부재).
    assert not hasattr(eng, "execute")


# ── Agent Lineage ──
def test_full_lineage_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.link_experiment(p.proposal_id, "EXP1", T1, commit=True)
    eng.link_validation("EXP1", "VAL1", T1, commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    exp = arts[M.artifact_id(M.ART_EXPERIMENT, "EXP1")]
    val = arts[M.artifact_id(M.ART_VALIDATION, "VAL1")]
    assert exp["parent_artifact"] == M.artifact_id(M.ART_PROPOSAL, p.proposal_id)
    assert val["parent_artifact"] == M.artifact_id(M.ART_EXPERIMENT, "EXP1")


def test_lineage_links_to_knowledge_graph_ref(tmp_path, monkeypatch):
    """experiment_ref 는 P10.5 kg entity_id 같은 상위 참조 문자열이 될 수 있다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    art = eng.link_experiment(p.proposal_id, "KGE:abc123", T1, commit=True)
    assert art["ref_id"] == "KGE:abc123"


# ── Report ──
def test_report_totals(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    eng.record_review(p.proposal_id, "human", APPROVE, "", T2, commit=True)
    eng.record_action("AG1", "EXECUTE_TRADE", "X", "", T0, commit=True)
    rep = eng.generate_report(T2)
    assert rep.agent_count == 1 and rep.request_count == 1 and rep.proposal_count == 1
    assert rep.review_count == 1 and rep.blocked_action_count == 1
    assert rep.proposal_state_distribution.get(ACCEPTED) == 1


def test_report_pending_reviews(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    rep = eng.generate_report(T2)
    assert rep.pending_reviews == 1


def test_report_provider_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng, "AG1")
    eng.register_agent("AG2", "n", "1", "openai", [M.READ_DATA], T0, commit=True)
    rep = eng.generate_report(T2)
    assert rep.provider_distribution.get("anthropic") == 1
    assert rep.provider_distribution.get("openai") == 1


def test_report_blocked_budget_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.set_budget("AG1", "P", 0, 0, T0, commit=True)
    eng.consume_budget("AG1", "P", M.KIND_EXPERIMENT, T1, commit=True)
    rep = eng.generate_report(T2)
    assert rep.blocked_budget_count == 1 and rep.budget_count == 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    _req(eng)
    assert eng.generate_report(T2).to_dict() == eng.generate_report(T2).to_dict()


def test_report_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().generate_report(T0)
    assert rep.agent_count == 0 and rep.pending_reviews == 0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.verify import verify_chain
    assert verify_chain()["ok"] is True


def _full_scenario(eng):
    _agent(eng)
    eng.activate_agent("AG1", T1, commit=True)
    eng.grant_capability("AG1", M.READ_DATA, T0, commit=True)
    r = eng.create_request("AG1", "obj", ["s1"], T0, commit=True)
    p = eng.create_proposal(r.request_id, "hyp", "m", "e", "r", T0, commit=True)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    eng.record_review(p.proposal_id, "human", APPROVE, "", T2, commit=True)
    eng.record_action("AG1", "GENERATE_REPORT", "R", "ok", T0, commit=True)
    eng.record_action("AG1", "PLACE_ORDER", "X", "", T1, commit=True)
    eng.set_budget("AG1", "P", 1, 1, T0, commit=True)
    eng.consume_budget("AG1", "P", M.KIND_EXPERIMENT, T1, commit=True)
    eng.link_experiment(p.proposal_id, "EXP1", T1, commit=True)
    return r, p


def test_verify_full_scenario_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.verify import verify_chain
    eng = _eng()
    _full_scenario(eng)
    res = verify_chain()
    assert res["ok"] is True
    assert res["lineage"]["ok"] is True and res["safety"]["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.verify import verify_chain
    eng = _eng()
    _agent(eng)
    recs = ledger.read_agent_events()
    recs[0]["provider"] = "TAMPERED"
    with open(sp("arg_agents.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.verify import verify_ledger
    eng = _eng()
    _agent(eng, "AG1")
    eng.register_agent("AG2", "n", "1", "p", [M.READ_DATA], T0, commit=True)
    recs = ledger.read_agent_events()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("arg_agents.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.AGENTS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.verify import verify_ledger
    eng = _eng()
    _agent(eng)
    recs = ledger.read_agent_events()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("arg_agents.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.AGENTS)["ok"] is False


def test_safety_audit_detects_forced_forbidden(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.verify import safety_audit
    # 위조: 금지 행동인데 result 가 BLOCKED 가 아닌 레코드를 직접 주입
    rec = {"action_id": "ACT:x", "agent_id": "AG1", "action_type": "EXECUTE_TRADE",
           "target": "AAPL", "result": "filled", "is_forbidden": True, "timestamp": T0,
           "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("arg_actions.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = safety_audit()
    assert res["ok"] is False
    assert any("forbidden_action_not_blocked" in i for i in res["issues"])


def test_safety_audit_detects_accept_without_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.verify import safety_audit
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    # 사람 검토 없이 상태만 강제 이동 (내부 API 오용 시뮬)
    meta = eng._proposal_meta(p.proposal_id)
    eng._emit_proposal_event(meta, SUBMITTED, REVIEWED, T2, actor="x", commit=True)
    eng._emit_proposal_event(meta, REVIEWED, ACCEPTED, T2, actor="x", commit=True)
    res = safety_audit()
    assert any("accepted_without_human_review" in i for i in res["issues"])


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.verify import replay
    eng = _eng()
    _full_scenario(eng)
    assert replay(eng, T2)["deterministic"] is True


# ── content hash ──
def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


# ── CLI ──
def test_cli_agent_and_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.__main__ import main
    rc = main(["agent", "--agent-id", "AG1", "--name", "R", "--version", "1", "--provider",
               "anthropic", "--capabilities", "READ_DATA,GENERATE_REPORT", "--activate",
               "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["agent"]["status"] in (REGISTERED, ACTIVE)
    main(["report"])
    rep = json.loads(capsys.readouterr().out)
    assert rep["agent_count"] == 1


def test_cli_capability_forbidden(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.__main__ import main
    main(["agent", "--agent-id", "AG1", "--name", "R", "--version", "1", "--provider", "p",
          "--commit"])
    capsys.readouterr()
    with pytest.raises(ForbiddenCapability):
        main(["capability", "--agent-id", "AG1", "--capability", "EXECUTE_TRADE", "--commit"])


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.__main__ import main
    main(["agent", "--agent-id", "AG1", "--name", "R", "--version", "1", "--provider", "p",
          "--commit"])
    capsys.readouterr()
    main(["request", "--agent-id", "AG1", "--objective", "find alpha", "--commit"])
    req = json.loads(capsys.readouterr().out)["request"]
    main(["propose", "--request-id", req["request_id"], "--hypothesis", "H", "--submit",
          "--commit"])
    prop = json.loads(capsys.readouterr().out)["proposal"]
    main(["review", "--proposal-id", prop["proposal_id"], "--reviewer", "human",
          "--decision", "APPROVE", "--commit"])
    rev = json.loads(capsys.readouterr().out)["review"]
    assert rev["decision"] == "APPROVE"
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_action_forbidden_blocked(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.__main__ import main
    main(["agent", "--agent-id", "AG1", "--name", "R", "--version", "1", "--provider", "p",
          "--commit"])
    capsys.readouterr()
    main(["action", "--agent-id", "AG1", "--action-type", "DEPLOY_STRATEGY", "--target", "S1",
          "--result", "deployed", "--commit"])
    out = json.loads(capsys.readouterr().out)["action"]
    assert out["result"] == M.ACTION_BLOCKED


def test_cli_budget_consume(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.__main__ import main
    main(["agent", "--agent-id", "AG1", "--name", "R", "--version", "1", "--provider", "p",
          "--commit"])
    main(["budget", "--agent-id", "AG1", "--period", "P", "--max-experiments", "1",
          "--max-queries", "1", "--commit"])
    capsys.readouterr()
    main(["consume", "--agent-id", "AG1", "--period", "P", "--kind", "experiment", "--commit"])
    capsys.readouterr()
    main(["consume", "--agent-id", "AG1", "--period", "P", "--kind", "experiment", "--commit"])
    out = json.loads(capsys.readouterr().out)["usage"]
    assert out["status"] == M.BUDGET_BLOCKED


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.agent_governance.__main__ import main
    main(["agent", "--agent-id", "AG1", "--name", "R", "--version", "1", "--provider", "p",
          "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.agent_governance.engine as eng_mod
    import jarvis.agent_governance.models as mdl_mod
    import jarvis.agent_governance.ledger as led_mod
    import jarvis.agent_governance.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "capital_allocation", _j + "strategy_deployment",
                 _j + "model_promotion", _j + "risk_governor",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "promote_model(", "change_permission("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_authority_api():
    api = set(dir(AgentGovernanceEngine))
    for banned in ("execute", "deploy", "place_order", "submit_order", "allocate",
                   "promote", "trade", "change_permission", "change_risk_threshold",
                   "modify_portfolio"):
        assert banned not in api


def test_agent_validated_not_approved_for_trading(tmp_path, monkeypatch):
    """Agent ACTIVE(=검증됨) 이어도 거래 승인/실행 권한은 전혀 없다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    eng.activate_agent("AG1", T1, commit=True)
    assert eng.agent_state("AG1") == ACTIVE
    assert not hasattr(eng, "approve_for_trading")
    assert not hasattr(eng, "grant_trading_permission")


def test_proposal_accepted_not_execution(tmp_path, monkeypatch):
    """Proposal ACCEPTED 는 실행 권한이 아니다 — 실행 경로 자체가 없다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _agent(eng)
    r = _req(eng)
    p = _prop(eng, r.request_id)
    eng.submit_proposal(p.proposal_id, T1, commit=True)
    eng.record_review(p.proposal_id, "human", APPROVE, "", T2, commit=True)
    assert eng.proposal_state(p.proposal_id) == ACCEPTED
    assert not hasattr(eng, "execute_proposal")
    assert not hasattr(eng, "deploy_proposal")


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.agent_governance.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_arg_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("arg_")


def test_no_collision_with_access_governance_ag_prefix():
    """P9.10 access_governance 의 ag_ 원장과 파일명이 충돌하지 않아야 한다."""
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    access_files = {"ag_operators.jsonl", "ag_roles.jsonl", "ag_sessions.jsonl",
                    "ag_access_requests.jsonl", "ag_approvals.jsonl", "ag_audit_reports.jsonl"}
    assert ours.isdisjoint(access_files)
    assert all(not fn.startswith("ag_") or fn.startswith("arg_") for fn in ours)


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 레이어 원장을 시드한 뒤 전체 워크플로를 돌려도 원본 해시 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"dg_datasets.jsonl": [{"dataset_id": "DS1"}],
             "kg_entities.jsonl": [{"entity_id": "KGE:1"}],
             "rg_strategies.jsonl": [{"strategy_id": "ST1"}]}
    hashes = {}
    for fn, rows in seeds.items():
        with open(sp(fn), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    _full_scenario(eng)
    # 상위 소스 읽기
    assert ledger.read_source("dg_datasets.jsonl")[0]["dataset_id"] == "DS1"
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_engine_only_appends_arg_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_scenario(eng)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("arg_") for f in created)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, files in ledger.SOURCE_LEDGERS.items():
        for fn in files:
            assert fn not in owned
