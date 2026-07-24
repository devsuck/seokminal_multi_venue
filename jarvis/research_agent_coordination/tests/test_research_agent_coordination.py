"""P26 research_agent_coordination 테스트 — 에이전트·역할·팀·세션/작업 생애주기·메시지·합의·
역할 분리·자기승인 방지·권한 경계·계보·verify·replay·CLI·보안·READ ONLY 상위. CONSENSUS ≠ APPROVAL."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_agent_coordination import ledger
from jarvis.research_agent_coordination import models as M
from jarvis.research_agent_coordination.engine import ResearchAgentCoordinator
from jarvis.research_agent_coordination.models import (
    CONSENSUS_VERDICTS,
    FORBIDDEN_VERBS,
    GENESIS,
    ROLE_EXAMPLES,
    SESSION_STATES,
    TASK_STATES,
    S_ACTIVE,
    S_ARCHIVED,
    S_CONCLUDED,
    S_CREATED,
    S_DISCUSSING,
    T_ARCHIVED,
    T_ASSIGNED,
    T_COMPLETED,
    T_CREATED,
    T_IN_PROGRESS,
    IllegalSessionTransition,
    IllegalTaskTransition,
    RoleSeparationError,
    TaskIsolationError,
    UnknownEntityError,
    agreement_score,
    can_session_transition,
    can_task_transition,
    classify_consensus,
    content_hash,
    contains_forbidden_action,
)
from jarvis.research_agent_coordination.verify import (
    consensus_integrity,
    duplicate_integrity,
    lineage_integrity,
    role_separation_integrity,
    session_lifecycle_integrity,
    task_lifecycle_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_agent_coordination.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchAgentCoordinator()


def _agent(e, name="analyst", version="1.0", now=T[0]):
    return e.register_agent(name, version, ["analysis"], "arg:agent:1", now, commit=True).agent_id


def _sess(e, objective="regime study", now=T[1]):
    return e.create_session(objective, "", now, commit=True).session_id


# ═══════════════ agent registration ═══════════════
def test_register_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_agent("analyst", "1.0", ["analysis"], "arg:1", T[0], commit=True)
    assert a.agent_id.startswith("RCA:")
    assert a.identity_hash.startswith("sha256:")


def test_agent_identity_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_agent("analyst", "1.0", ["x"], "s", T[0], commit=True)
    b = e.register_agent("analyst", "1.0", ["DIFFERENT"], "other", T[1], commit=True)
    assert a.agent_id == b.agent_id
    assert a.identity_hash == b.identity_hash  # 최초 정체성 유지
    assert len([x for x in ledger.read_agents() if x["agent_id"] == a.agent_id]) == 1


def test_agent_version_distinct(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_agent("analyst", "1.0", now=T[0], commit=True).agent_id
    b = e.register_agent("analyst", "2.0", now=T[1], commit=True).agent_id
    assert a != b


def test_agent_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e)
    assert any(a["artifact_type"] == "AGENT" for a in ledger.read_artifacts())


def test_list_agents(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "a")
    _agent(e, "b")
    assert len(e.list_agents()) == 2


def test_agent_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_agent("a", "1.0", now=T[0], commit=False)
    assert ledger.read_agents() == []


# ═══════════════ role validation / separation ═══════════════
def test_define_role(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().define_role("DATA_ANALYST", "analyze data", ["read", "summarize"], T[0], commit=True)
    assert r.role_id.startswith("RCO:")
    assert r.allowed_actions == ["read", "summarize"]


def test_role_separation_rejects_forbidden(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(RoleSeparationError):
        _eng().define_role("BAD", "x", ["read", "deploy_strategy"], T[0], commit=True)


@pytest.mark.parametrize("action", ["execute_trade", "change_permission", "approve_for_trading",
                                    "allocate_capital", "deploy"])
def test_role_forbidden_actions(tmp_path, monkeypatch, action):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(RoleSeparationError):
        _eng().define_role("R", "x", [action], T[0], commit=True)


def test_role_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.define_role("R", "x", ["read"], T[0], commit=True).role_id
    b = e.define_role("R", "y", ["write"], T[1], commit=True).role_id
    assert a == b
    assert len(ledger.read_roles()) == 1


@pytest.mark.parametrize("role", ROLE_EXAMPLES)
def test_role_examples_allowed(tmp_path, monkeypatch, role):
    _iso(tmp_path, monkeypatch)
    r = _eng().define_role(role, "resp", ["read", "analyze"], T[0], commit=True)
    assert r.name == role


def test_contains_forbidden_action():
    assert contains_forbidden_action(["read", "execute"]) is True
    assert contains_forbidden_action(["read", "summarize"]) is False


# ═══════════════ team creation ═══════════════
def test_create_team(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    t = e.create_team("alpha study", [ag], T[1], commit=True)
    assert t.team_id.startswith("RCT:")
    assert t.members == [ag]


def test_team_unknown_member(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().create_team("obj", ["RCA:nope"], T[0], commit=True)


def test_team_empty_members(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _eng().create_team("obj", [], T[0], commit=True)
    assert t.members == []


# ═══════════════ session lifecycle ═══════════════
def test_create_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_session("obj", "", T[0], commit=True)
    assert ev.to_state == S_CREATED
    assert ev.session_id.startswith("RCS:")
    assert ev.session_event_id.startswith("RCE:")


def test_session_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.activate_session(sess, now=T[2], commit=True)
    e.start_discussion(sess, now=T[3], commit=True)
    e.conclude_session(sess, now=T[4], commit=True)
    e.archive_session(sess, now=T[5], commit=True)
    assert e.session_state(sess) == S_ARCHIVED


def test_session_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    with pytest.raises(IllegalSessionTransition):
        e.archive_session(sess, now=T[2], commit=True)  # CREATED→ARCHIVED skip


def test_session_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_session("o", "", T[0], commit=True).session_id
    b = e.create_session("o", "", T[1], commit=True).session_id
    assert a == b
    assert len(ledger.session_events(a)) == 1


def test_session_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().activate_session("RCS:nope", now=T[1], commit=True)


def test_sessions_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.activate_session(sess, now=T[2], commit=True)
    assert sess in e.sessions_in_state(S_ACTIVE)


@pytest.mark.parametrize("frm,to,ok", [
    (S_CREATED, S_ACTIVE, True), (S_CREATED, S_DISCUSSING, False),
    (S_ACTIVE, S_DISCUSSING, True), (S_ACTIVE, S_CONCLUDED, True),
    (S_DISCUSSING, S_CONCLUDED, True), (S_DISCUSSING, S_ACTIVE, True),
    (S_CONCLUDED, S_ARCHIVED, True), (S_ARCHIVED, S_ACTIVE, False),
])
def test_session_transition_matrix(frm, to, ok):
    assert can_session_transition(frm, to) is ok


@pytest.mark.parametrize("s", SESSION_STATES)
def test_session_states(s):
    assert s in SESSION_STATES


# ═══════════════ task assignment / lifecycle ═══════════════
def test_assign_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    tk = e.assign_task(sess, ag, "analyze regime data", "kg:1", [], T[2], commit=True)
    assert tk.task_id.startswith("RCK:")
    assert tk.to_state == T_ASSIGNED
    assert tk.assigned_agent == ag


def test_task_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    tk = e.assign_task(sess, ag, "obj", now=T[2], commit=True).task_id
    e.start_task(tk, now=T[3], commit=True)
    e.complete_task(tk, now=T[4], commit=True)
    e.archive_task(tk, now=T[5], commit=True)
    assert e.task_state(tk) == T_ARCHIVED


def test_task_requires_owner(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    with pytest.raises(TaskIsolationError):
        e.assign_task(sess, "", "obj", now=T[2], commit=True)


def test_task_requires_objective(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    with pytest.raises(TaskIsolationError):
        e.assign_task(sess, ag, "", now=T[2], commit=True)


def test_task_forbidden_objective(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    with pytest.raises(RoleSeparationError):
        e.assign_task(sess, ag, "execute_trade", now=T[2], commit=True)


def test_task_unknown_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    with pytest.raises(UnknownEntityError):
        e.assign_task(sess, "RCA:nope", "obj", now=T[2], commit=True)


def test_task_unknown_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    with pytest.raises(UnknownEntityError):
        e.assign_task("RCS:nope", ag, "obj", now=T[2], commit=True)


def test_task_dependencies(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    t1 = e.assign_task(sess, ag, "dep task", now=T[2], commit=True).task_id
    t2 = e.assign_task(sess, ag, "main task", "src", [t1], T[3], commit=True).task_id
    res = e.resolve_dependencies(t2)
    assert res["ready"] is False  # t1 아직 미완료
    e.start_task(t1, now=T[4], commit=True)
    e.complete_task(t1, now=T[5], commit=True)
    assert e.resolve_dependencies(t2)["ready"] is True


def test_task_lineage_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    tk = e.assign_task(sess, ag, "obj", now=T[2], commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    task_art = next(a for a in arts.values() if a["ref_id"] == tk.task_id)
    assert task_art["parent_artifact"] == M.artifact_id(M.ART_AGENT, ag)


@pytest.mark.parametrize("frm,to,ok", [
    (T_CREATED, T_ASSIGNED, True), (T_CREATED, T_IN_PROGRESS, False),
    (T_ASSIGNED, T_IN_PROGRESS, True), (T_IN_PROGRESS, T_COMPLETED, True),
    (T_COMPLETED, T_ARCHIVED, True), (T_ARCHIVED, T_IN_PROGRESS, False),
])
def test_task_transition_matrix(frm, to, ok):
    assert can_task_transition(frm, to) is ok


@pytest.mark.parametrize("s", TASK_STATES)
def test_task_states(s):
    assert s in TASK_STATES


# ═══════════════ message lineage ═══════════════
def test_record_message(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    m = e.record_message(sess, ag, "regime filter looks promising", ["kg:1"], T[2], commit=True)
    assert m.message_id.startswith("RCM:")
    assert m.refs == ["kg:1"]


def test_message_unknown_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_message("RCS:nope", "RCA:x", "hi", now=T[0], commit=True)


def test_messages_in_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    e.record_message(sess, ag, "m1", now=T[2], commit=True)
    e.record_message(sess, ag, "m2", now=T[3], commit=True)
    assert len(ledger.messages_in_session(sess)) == 2


def test_message_lineage_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    m = e.record_message(sess, ag, "c", now=T[2], commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    msg_art = next(a for a in arts.values() if a["ref_id"] == m.message_id)
    assert msg_art["parent_artifact"] == M.artifact_id(M.ART_SESSION, sess)


# ═══════════════ consensus (record only) ═══════════════
def test_record_consensus(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    c = e.record_consensus(sess, {"a1": "YES", "a2": "YES"}, "agree on regime filter", T[2],
                           commit=True)
    assert c.consensus_id.startswith("RCC:")
    assert c.verdict == "YES"
    assert c.agreement_score == 1.0
    assert c.is_decision is False


def test_consensus_mixed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    c = e.record_consensus(sess, {"a1": "YES", "a2": "NO"}, "", T[2], commit=True)
    assert c.verdict == "MIXED"
    assert c.agreement_score == 0.5


def test_consensus_no(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    c = e.record_consensus(sess, {"a1": "NO", "a2": "NO"}, "", T[2], commit=True)
    assert c.verdict == "NO"


def test_consensus_never_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    c = e.record_consensus(sess, {"a1": "YES", "a2": "YES", "a3": "YES"}, "", T[2], commit=True)
    assert c.is_decision is False  # 만장일치 YES 여도 자동 결정/배포/선택 없음


def test_consensus_unknown_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_consensus("RCS:nope", {"a": "YES"}, now=T[0], commit=True)


@pytest.mark.parametrize("v", CONSENSUS_VERDICTS)
def test_consensus_verdicts(v):
    assert v in CONSENSUS_VERDICTS


def test_agreement_score_empty():
    assert agreement_score({}) == 0.0


@pytest.mark.parametrize("score,verdict", [(1.0, "YES"), (0.0, "NO"), (0.5, "MIXED"), (0.9, "MIXED")])
def test_classify_consensus(score, verdict):
    assert classify_consensus(score) == verdict


# ═══════════════ self-approval / permission boundary ═══════════════
def test_no_self_approval_via_role(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(RoleSeparationError):
        _eng().define_role("SELF", "x", ["self_approve"], T[0], commit=True)


def test_no_permission_change_via_role(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(RoleSeparationError):
        _eng().define_role("PERM", "x", ["change_permission"], T[0], commit=True)


def test_no_governance_modify_via_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    with pytest.raises(RoleSeparationError):
        e.assign_task(sess, ag, "modify_governance", now=T[2], commit=True)


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("knowledge_graph", "agent_governance", "decision_intelligence", "simulation",
              "research_automation", "monitoring", "reliability", "autonomous_research"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("arg_agents.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"agent_id": f"a{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("agent_governance") == 3
    assert open(p).read() == before


def test_source_ref_exists(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("arg_agents.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps({"agent_id": "arg:a1"}) + "\n")
    assert ledger.source_ref_exists("agent_governance", "arg:a1") is True
    assert ledger.source_ref_exists("agent_governance", "arg:zz") is False


def test_all_source_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    counts = ledger.all_source_counts()
    assert set(counts) == set(ledger.SOURCE_LAYERS)


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    e.define_role("DATA_ANALYST", "d", ["read"], T[1], commit=True)
    e.create_team("obj", [ag], T[2], commit=True)
    sess = _sess(e)
    e.activate_session(sess, now=T[3], commit=True)
    tk = e.assign_task(sess, ag, "obj", now=T[4], commit=True).task_id
    e.start_task(tk, now=T[5], commit=True)
    e.record_message(sess, ag, "finding", now=T[6], commit=True)
    e.record_consensus(sess, {"a": "YES"}, "", T[7], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e)
    p = sp("racd_agents.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "a")
    _agent(e, "b")
    p = sp("racd_agents.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate_session(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _sess(e)
    p = sp("racd_sessions.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_session_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.activate_session(sess, now=T[2], commit=True)
    assert session_lifecycle_integrity()["ok"] is True


def test_task_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    e.assign_task(sess, ag, "obj", now=T[2], commit=True)
    assert task_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _agent(e, "a")
    _agent(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_role_separation_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.define_role("R", "x", ["read", "analyze"], T[0], commit=True)
    assert role_separation_integrity()["ok"] is True


def test_role_separation_integrity_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.define_role("R", "x", ["read"], T[0], commit=True)
    p = sp("racd_roles.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["allowed_actions"] = ["deploy_strategy"]
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert role_separation_integrity()["ok"] is False


def test_consensus_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.record_consensus(sess, {"a": "YES"}, "", T[2], commit=True)
    assert consensus_integrity()["ok"] is True


def test_consensus_integrity_detects_decision(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.record_consensus(sess, {"a": "YES"}, "", T[2], commit=True)
    p = sp("racd_consensus.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_decision"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert consensus_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    e.assign_task(sess, ag, "obj", now=T[2], commit=True)
    e.record_message(sess, ag, "c", now=T[3], commit=True)
    e.record_consensus(sess, {"a": "YES"}, "", T[4], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    e.record_consensus(sess, {ag: "YES"}, "", T[2], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    e.record_consensus(sess, {"a": "YES", "b": "NO"}, "", T[2], commit=True)
    r = e.generate_report("SYSTEM", T[3], commit=True)
    assert r.report_id.startswith("RCR:")
    assert r.is_binding is False
    assert r.agent_count == 1
    assert r.consensus_count == 1
    assert r.verdict_distribution.get("MIXED") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "APPROVAL" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["ANALYZE", "DISCUSS", "COORDINATE", "SUMMARIZE", "RECORD",
                                  "REVIEW"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "ACTIVATE_LIVE", "APPROVE_FOR_TRADING",
                                "CHANGE_PERMISSION", "SELF_APPROVE"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.agent_id, ("n", "1.0"), "RCA:"),
    (M.role_id, ("R",), "RCO:"),
    (M.team_id, ("o",), "RCT:"),
    (M.session_id, ("o",), "RCS:"),
    (M.session_event_id, ("s", "CREATED", 0), "RCE:"),
    (M.task_id, ("s", "o"), "RCK:"),
    (M.task_event_id, ("t", "CREATED", 0), "RCX:"),
    (M.message_id, ("s", "a", 0), "RCM:"),
    (M.consensus_id, ("s", 0), "RCC:"),
    (M.report_id, ("s", "t"), "RCR:"),
    (M.artifact_id, ("AGENT", "r"), "RCF:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_ids_deterministic():
    assert M.agent_id("n", "1.0") == M.agent_id("n", "1.0")


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ag = _agent(e)
    sess = _sess(e)
    e.assign_task(sess, ag, "obj", now=T[2], commit=True)
    e.record_consensus(sess, {"a": "YES"}, "", T[3], commit=True)
    s = e.summary(T[9])
    assert s.agent_count == 1
    assert s.task_count == 1
    assert s.consensus_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_agent(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordination.__main__ import main
    assert main(["agent", "--name", "analyst", "--version", "1.0", "--capabilities", "a|b",
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["agent"]["agent_id"].startswith("RCA:")


def test_cli_role(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordination.__main__ import main
    assert main(["role", "--name", "DATA_ANALYST", "--actions", "read|analyze", "--commit"]) == 0


def test_cli_session_and_task(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordination.__main__ import main
    main(["agent", "--name", "a", "--version", "1.0", "--commit"])
    ag = json.loads(capsys.readouterr().out)["agent"]["agent_id"]
    main(["session", "--objective", "study", "--commit"])
    sess = json.loads(capsys.readouterr().out)["session"]["session_id"]
    assert main(["task", "--session", sess, "--agent", ag, "--objective", "analyze",
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["task"]["to_state"] == "ASSIGNED"


def test_cli_message_and_consensus(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordination.__main__ import main
    main(["session", "--objective", "s", "--commit"])
    sess = json.loads(capsys.readouterr().out)["session"]["session_id"]
    assert main(["message", "--session", sess, "--agent", "RCA:x", "--content", "hi",
                 "--commit"]) == 0
    capsys.readouterr()
    assert main(["consensus", "--session", sess, "--positions", "a:YES|b:NO", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["consensus"]["is_decision"] is False


def test_cli_team(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordination.__main__ import main
    assert main(["team", "--objective", "study", "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordination.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordination.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordination.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_agent_coordination.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_agent("a", "1.0", now=T[0], commit=True)
    with pytest.raises(Exception):
        a.name = "x"


def test_nine_ledgers():
    assert len(ledger.ALL_LEDGERS) == 9


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("racd_")


def test_no_rac_prefix_collision():
    # rac_ 는 기존 소유 → racd_ 사용(충돌 회피)
    for fname, _ in ledger.ALL_LEDGERS:
        assert not fname.startswith("rac_") or fname.startswith("racd_")
        assert fname.startswith("racd_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("racd_agents.jsonl", "racd_roles.jsonl", "racd_teams.jsonl", "racd_sessions.jsonl",
                "racd_tasks.jsonl", "racd_messages.jsonl", "racd_consensus.jsonl",
                "racd_reports.jsonl", "racd_artifacts.jsonl"):
        assert req in names


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_trading", "jarvis.portfolio_execution",
    "jarvis.live_portfolio", "jarvis.portfolio", "jarvis.order", "jarvis.deployment", "jarvis.live",
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
    bad = ("execute", "deploy", "trade", "allocate", "approve_live", "change_permission",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "activate_live",
           "approve_for_trading")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def purge_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


def test_engine_no_forbidden_methods():
    e = _eng()
    for attr in ("execute", "deploy", "trade", "allocate", "approve_live", "change_permission"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 상위 소스 시드(READ ONLY 대상): P10.6 agent governance
    with open(sp("arg_agents.jsonl"), "w") as f:
        f.write(json.dumps({"agent_id": "arg:analyst"}) + "\n")
    e = _eng()
    # 에이전트 등록(정체성 불변; 권한은 P10.6 소유)
    a1 = e.register_agent("data-analyst", "1.0", ["analysis"], "arg:analyst", T[0], commit=True).agent_id
    a2 = e.register_agent("validation-reviewer", "1.0", ["validation"], "arg:reviewer", T[1],
                          commit=True).agent_id
    # 역할 정의(금지 행동 불가)
    e.define_role("DATA_ANALYST", "analyze", ["read", "summarize"], T[2], commit=True)
    e.define_role("VALIDATION_REVIEWER", "validate", ["review", "flag"], T[3], commit=True)
    # 팀 구성
    e.create_team("regime-filter study", [a1, a2], T[4], commit=True)
    # 세션 → 활성 → 토론
    sess = e.create_session("does regime filter improve robustness?", "", T[5], commit=True).session_id
    e.activate_session(sess, now=T[6], commit=True)
    # 작업 배분(owner·objective·lineage 필수)
    t1 = e.assign_task(sess, a1, "analyze regime transitions", "kg:regimes", [], T[7],
                       commit=True).task_id
    t2 = e.assign_task(sess, a2, "validate robustness", "sim:1", [t1], T[8], commit=True).task_id
    e.start_task(t1, now=T[9], commit=True)
    e.complete_task(t1, now=T[10], commit=True)
    assert e.resolve_dependencies(t2)["ready"] is True
    # 토론 메시지(계보)
    e.record_message(sess, a1, "regime filter cuts drawdown", ["kg:regimes"], T[11], commit=True)
    e.record_message(sess, a2, "robustness holds OOS", ["sim:1"], T[12], commit=True)
    e.start_discussion(sess, now=T[13], commit=True)
    # 합의 기록(만장일치 YES 여도 자동 결정/배포/선택 없음)
    c = e.record_consensus(sess, {a1: "YES", a2: "YES"}, "adopt as research direction", T[14],
                           commit=True)
    assert c.verdict == "YES"
    assert c.is_decision is False  # CONSENSUS ≠ APPROVAL/DEPLOYMENT
    e.conclude_session(sess, now=T[15], commit=True)
    # 리포트
    r = e.generate_report("SYSTEM", T[16], commit=True)
    assert r.agent_count == 2
    assert r.consensus_count == 1
    assert r.is_binding is False
    e.archive_session(sess, now=T[17], commit=True)
    assert e.session_state(sess) == S_ARCHIVED
    assert open(sp("arg_agents.jsonl")).read()  # 상위 원장 여전히 존재·불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[18])["deterministic"] is True
