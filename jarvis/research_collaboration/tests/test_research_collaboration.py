"""P19 research_collaboration 테스트 — 협업/참여/제안/합의/갈등/사람검토 생애주기·메시지 불변·
동료검토·계보·verify·replay·CLI·보안·금지능력."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_collaboration import ledger
from jarvis.research_collaboration import models as M
from jarvis.research_collaboration.engine import ResearchCollaborationEngine
from jarvis.research_collaboration.models import (
    COLLAB_STATES,
    CONFLICT_TYPES,
    CONSENSUS_STATES,
    FORBIDDEN_VERBS,
    GENESIS,
    HUMAN_REVIEW_STATES,
    MESSAGE_TYPES,
    PARTICIPATION_STATES,
    PROPOSAL_STATES,
    REVIEW_CATEGORIES,
    HumanReviewRequired,
    IllegalTransition,
    ImmutableRecordError,
    ReviewerRequired,
    UnknownEntityError,
    can_collab_transition,
    can_consensus_transition,
    can_human_review_transition,
    can_participation_transition,
    can_proposal_transition,
    content_hash,
    is_forbidden_verb,
)
from jarvis.research_collaboration.verify import (
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
    monkeypatch.setattr("jarvis.research_collaboration.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchCollaborationEngine()


def _collab(e, name="c1", now=T[0]):
    return e.create_collaboration(name, "obj", now, commit=True).collaboration_id


def _active(e, name="c1"):
    cid = _collab(e, name)
    e.form_collaboration(cid, T[1], commit=True)
    e.activate_collaboration(cid, T[2], commit=True)
    return cid


# ═══════════════ collaboration lifecycle ═══════════════
def test_create_collaboration(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_collaboration("c", "o", T[0], commit=True)
    assert ev.to_state == "CREATED"
    assert ev.collaboration_id.startswith("CXB:")
    assert ev.collab_event_id.startswith("CXL:")


def test_collab_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_collaboration("c", "o", T[0], commit=True).collaboration_id
    b = e.create_collaboration("c", "o", T[1], commit=True).collaboration_id
    assert a == b
    assert len(ledger.collab_events(a)) == 1


def test_collab_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_collaboration("c", "o1", T[0], commit=True)
    with pytest.raises(ImmutableRecordError):
        e.create_collaboration("c", "o2", T[1], commit=True)


def test_collab_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _collab(e)
    e.form_collaboration(cid, T[1], commit=True)
    e.activate_collaboration(cid, T[2], commit=True)
    e.review_collaboration(cid, T[3], commit=True)
    e.complete_collaboration(cid, T[4], commit=True)
    e.archive_collaboration(cid, T[5], commit=True)
    assert e.collaboration_state(cid) == "ARCHIVED"


def test_collab_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _collab(e)
    with pytest.raises(IllegalTransition):
        e.activate_collaboration(cid, T[1], commit=True)  # CREATED→ACTIVE skip


def test_collab_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_collaboration("c", "o", T[0], commit=False)
    assert ledger.read_collab_events() == []


def test_collab_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _collab(e)
    assert any(a["artifact_type"] == "COLLABORATION" for a in ledger.read_artifacts())


def test_collab_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().form_collaboration("CXB:nope", T[1], commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    ("CREATED", "FORMING", True), ("CREATED", "ACTIVE", False),
    ("FORMING", "ACTIVE", True), ("ACTIVE", "REVIEWING", True),
    ("REVIEWING", "COMPLETED", True), ("REVIEWING", "ACTIVE", True),
    ("COMPLETED", "ARCHIVED", True), ("ARCHIVED", "ACTIVE", False),
])
def test_collab_transition_matrix(frm, to, ok):
    assert can_collab_transition(frm, to) is ok


@pytest.mark.parametrize("s", COLLAB_STATES)
def test_collab_states(s):
    assert s in COLLAB_STATES


# ═══════════════ participation ═══════════════
def test_invite_participant(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    p = e.invite_participant(cid, "agent1", "lead", "alpha", "", T[3], commit=True)
    assert p.participant_id.startswith("CXU:")
    assert p.to_state == "INVITED"
    assert p.agent_id == "agent1"


def test_participation_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    pid = e.invite_participant(cid, "a", now=T[3], commit=True).participant_id
    e.accept_participation(pid, T[4], commit=True)
    e.activate_participation(pid, T[5], commit=True)
    e.complete_participation(pid, T[6], commit=True)
    assert e.participation_state(pid) == "COMPLETED"


def test_participation_invalid(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    pid = e.invite_participant(cid, "a", now=T[3], commit=True).participant_id
    with pytest.raises(IllegalTransition):
        e.activate_participation(pid, T[4], commit=True)  # INVITED→ACTIVE skip


def test_participation_remove(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    pid = e.invite_participant(cid, "a", now=T[3], commit=True).participant_id
    e.remove_participation(pid, T[4], commit=True)
    assert e.participation_state(pid) == "REMOVED"


def test_invite_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    a = e.invite_participant(cid, "a", now=T[3], commit=True).participant_id
    b = e.invite_participant(cid, "a", now=T[4], commit=True).participant_id
    assert a == b


def test_invite_archived_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _collab(e)
    e.form_collaboration(cid, T[1], commit=True)
    e.activate_collaboration(cid, T[2], commit=True)
    e.review_collaboration(cid, T[3], commit=True)
    e.complete_collaboration(cid, T[4], commit=True)
    with pytest.raises(IllegalTransition):
        e.invite_participant(cid, "late", now=T[5], commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    ("INVITED", "ACCEPTED", True), ("INVITED", "ACTIVE", False),
    ("ACCEPTED", "ACTIVE", True), ("ACTIVE", "PAUSED", True), ("ACTIVE", "COMPLETED", True),
    ("PAUSED", "ACTIVE", True), ("COMPLETED", "ACTIVE", False), ("REMOVED", "ACTIVE", False),
])
def test_participation_matrix(frm, to, ok):
    assert can_participation_transition(frm, to) is ok


@pytest.mark.parametrize("s", PARTICIPATION_STATES)
def test_participation_states(s):
    assert s in PARTICIPATION_STATES


# ═══════════════ messages (immutable) ═══════════════
def test_post_message(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    m = e.post_message(cid, "agent1", "HYPOTHESIS", "H1", ["art1"], {}, T[3], commit=True)
    assert m.message_id.startswith("CXM:")
    assert m.message_type == "HYPOTHESIS"
    assert m.reference_artifacts == ["art1"]


def test_message_content_hashed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    m = e.post_message(cid, "a", "EVIDENCE", "secret content", now=T[3], commit=True)
    assert m.payload_hash.startswith("sha256:")
    assert "secret content" not in json.dumps(m.to_dict())


def test_message_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.post_message(cid, "a", "QUESTION", "q", now=T[3], commit=True)
    e.post_message(cid, "a", "RESULT", "r", now=T[4], commit=True)
    assert len(ledger.collab_messages(cid)) == 2


def test_message_unknown_collab(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().post_message("CXB:nope", "a", "QUESTION", "q", now=T[3], commit=True)


@pytest.mark.parametrize("mt", MESSAGE_TYPES)
def test_message_types(mt):
    assert mt in MESSAGE_TYPES


# ═══════════════ proposals ═══════════════
def test_create_proposal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    p = e.create_proposal(cid, "a", "prop1", T[3], commit=True)
    assert p.proposal_id.startswith("CXO:")
    assert p.to_state == "DRAFT"


def test_proposal_lifecycle_to_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    prid = e.create_proposal(cid, "a", "p", T[3], commit=True).proposal_id
    e.submit_proposal(prid, T[4], commit=True)
    e.discuss_proposal(prid, T[5], commit=True)
    e.review_proposal(prid, T[6], commit=True)
    assert e.proposal_state(prid) == "REVIEWED"


def test_proposal_accept_requires_review_or_consensus(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    prid = e.create_proposal(cid, "a", "p", T[3], commit=True).proposal_id
    e.submit_proposal(prid, T[4], commit=True)
    e.discuss_proposal(prid, T[5], commit=True)
    e.review_proposal(prid, T[6], commit=True)
    # 사람검토/합의 없음 → 승인 차단(자동 승인 없음)
    with pytest.raises(HumanReviewRequired):
        e.accept_proposal(prid, T[7], commit=True)


def test_proposal_accept_with_human_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    prid = e.create_proposal(cid, "a", "p", T[3], commit=True).proposal_id
    e.submit_proposal(prid, T[4], commit=True)
    e.discuss_proposal(prid, T[5], commit=True)
    e.review_proposal(prid, T[6], commit=True)
    # 사람검토 CLOSED 진행
    hr = e.request_human_review(cid, "p", T[7], commit=True).human_review_id
    e.assign_human_review(hr, "dr.human", T[8], commit=True)
    e.start_human_review(hr, T[9], commit=True)
    e.comment_human_review(hr, "ok", T[10], commit=True)
    e.close_human_review(hr, T[11], commit=True)
    ev = e.accept_proposal(prid, T[12], commit=True)
    assert ev.to_state == "ACCEPTED"
    assert ev.basis == "human_review"


def test_proposal_accept_with_consensus(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    prid = e.create_proposal(cid, "a", "p", T[3], commit=True).proposal_id
    e.submit_proposal(prid, T[4], commit=True)
    e.discuss_proposal(prid, T[5], commit=True)
    e.review_proposal(prid, T[6], commit=True)
    cons = e.open_consensus(cid, "topic", T[7], commit=True).consensus_id
    e.discuss_consensus(cons, {}, T[8], commit=True)
    e.tentative_consensus(cons, {}, T[9], commit=True)
    e.review_consensus(cons, {}, T[10], commit=True)
    e.record_consensus(cons, {"AGREEMENT": 3}, T[11], commit=True)
    ev = e.accept_proposal(prid, T[12], commit=True)
    assert ev.basis == "consensus"


def test_proposal_reject(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    prid = e.create_proposal(cid, "a", "p", T[3], commit=True).proposal_id
    e.submit_proposal(prid, T[4], commit=True)
    e.discuss_proposal(prid, T[5], commit=True)
    e.review_proposal(prid, T[6], commit=True)
    e.reject_proposal(prid, T[7], commit=True)
    assert e.proposal_state(prid) == "REJECTED"


def test_proposal_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    prid = e.create_proposal(cid, "a", "p", T[3], commit=True).proposal_id
    with pytest.raises(IllegalTransition):
        e.review_proposal(prid, T[4], commit=True)  # DRAFT→REVIEWED skip


@pytest.mark.parametrize("frm,to,ok", [
    ("DRAFT", "SUBMITTED", True), ("DRAFT", "REVIEWED", False),
    ("SUBMITTED", "DISCUSSION", True), ("DISCUSSION", "REVIEWED", True),
    ("REVIEWED", "ACCEPTED", True), ("REVIEWED", "REJECTED", True),
    ("ACCEPTED", "REJECTED", False),
])
def test_proposal_matrix(frm, to, ok):
    assert can_proposal_transition(frm, to) is ok


# ═══════════════ peer review ═══════════════
def test_add_peer_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    r = e.add_peer_review(cid, "rev1", "prop1", "methodology", 0.8, "good", ["e1"], T[3],
                          commit=True)
    assert r.review_id.startswith("CXV:")
    assert r.is_binding is False
    assert r.category == "methodology"


def test_peer_review_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.add_peer_review(cid, "r", "t", "risk", 0.5, now=T[3], commit=True)
    e.add_peer_review(cid, "r", "t", "risk", 0.6, now=T[4], commit=True)
    assert len(ledger.read_reviews()) == 2


@pytest.mark.parametrize("cat", REVIEW_CATEGORIES)
def test_review_categories(cat):
    assert cat in REVIEW_CATEGORIES


# ═══════════════ consensus ═══════════════
def test_open_consensus(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    c = e.open_consensus(cid, "topic", T[3], commit=True)
    assert c.consensus_id.startswith("CXG:")
    assert c.to_state == "OPEN"
    assert c.is_approval is False


def test_consensus_full(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    cons = e.open_consensus(cid, "t", T[3], commit=True).consensus_id
    e.discuss_consensus(cons, {"AGREEMENT": 2}, T[4], commit=True)
    e.tentative_consensus(cons, {}, T[5], commit=True)
    e.review_consensus(cons, {}, T[6], commit=True)
    r = e.record_consensus(cons, {"AGREEMENT": 3, "MINORITY_OPINION": ["x"]}, T[7], commit=True)
    assert e.consensus_state(cons) == "RECORDED"
    assert r.is_approval is False  # 합의 ≠ 승인


def test_consensus_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    cons = e.open_consensus(cid, "t", T[3], commit=True).consensus_id
    with pytest.raises(IllegalTransition):
        e.record_consensus(cons, {}, T[4], commit=True)  # OPEN→RECORDED skip


@pytest.mark.parametrize("frm,to,ok", [
    ("OPEN", "DISCUSSION", True), ("OPEN", "RECORDED", False),
    ("DISCUSSION", "TENTATIVE", True), ("TENTATIVE", "REVIEWED", True),
    ("REVIEWED", "RECORDED", True), ("RECORDED", "OPEN", False),
])
def test_consensus_matrix(frm, to, ok):
    assert can_consensus_transition(frm, to) is ok


@pytest.mark.parametrize("s", CONSENSUS_STATES)
def test_consensus_states(s):
    assert s in CONSENSUS_STATES


# ═══════════════ conflict ═══════════════
def test_open_conflict(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    c = e.open_conflict(cid, "DATA", "disagree on data", T[3], commit=True)
    assert c.conflict_id.startswith("CXK:")
    assert c.to_state == "OPEN"


def test_conflict_full(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    conf = e.open_conflict(cid, "METHOD", "d", T[3], commit=True).conflict_id
    e.analyze_conflict(conf, T[4], commit=True)
    e.resolve_conflict(conf, "documented both views", T[5], commit=True)
    e.document_conflict(conf, "both recorded", T[6], commit=True)
    assert e.conflict_state(conf) == "DOCUMENTED"


def test_conflict_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    conf = e.open_conflict(cid, "DATA", "d", T[3], commit=True).conflict_id
    with pytest.raises(IllegalTransition):
        e.document_conflict(conf, "", T[4], commit=True)  # OPEN→DOCUMENTED skip


@pytest.mark.parametrize("ct", CONFLICT_TYPES)
def test_conflict_types(ct):
    assert ct in CONFLICT_TYPES


# ═══════════════ human review ═══════════════
def test_request_human_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    hr = e.request_human_review(cid, "prop1", T[3], commit=True)
    assert hr.human_review_id.startswith("CXW:")
    assert hr.to_state == "REQUESTED"


def test_human_review_requires_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    hr = e.request_human_review(cid, "p", T[3], commit=True).human_review_id
    with pytest.raises(ReviewerRequired):
        e.assign_human_review(hr, "", T[4], commit=True)  # 익명 승인 금지


def test_human_review_full(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    hr = e.request_human_review(cid, "p", T[3], commit=True).human_review_id
    e.assign_human_review(hr, "dr.jane", T[4], commit=True)
    e.start_human_review(hr, T[5], commit=True)
    e.comment_human_review(hr, "looks solid", T[6], commit=True)
    e.close_human_review(hr, T[7], commit=True)
    assert e.human_review_state(hr) == "CLOSED"


def test_human_review_reviewer_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    hr = e.request_human_review(cid, "p", T[3], commit=True).human_review_id
    ev = e.assign_human_review(hr, "dr.jane", T[4], commit=True)
    assert ev.reviewer == "dr.jane"


def test_human_review_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    hr = e.request_human_review(cid, "p", T[3], commit=True).human_review_id
    with pytest.raises(IllegalTransition):
        e.close_human_review(hr, T[4], commit=True)  # REQUESTED→CLOSED skip


@pytest.mark.parametrize("frm,to,ok", [
    ("REQUESTED", "ASSIGNED", True), ("REQUESTED", "CLOSED", False),
    ("ASSIGNED", "UNDER_REVIEW", True), ("UNDER_REVIEW", "COMMENTED", True),
    ("COMMENTED", "CLOSED", True), ("CLOSED", "ASSIGNED", False),
])
def test_human_review_matrix(frm, to, ok):
    assert can_human_review_transition(frm, to) is ok


@pytest.mark.parametrize("s", HUMAN_REVIEW_STATES)
def test_human_review_states(s):
    assert s in HUMAN_REVIEW_STATES


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.invite_participant(cid, "a", now=T[3], commit=True)
    e.post_message(cid, "a", "HYPOTHESIS", "h", now=T[4], commit=True)
    r = e.generate_report(cid, "COLLABORATION", T[5], commit=True)
    assert r.report_id.startswith("CXN:")
    assert r.is_binding is False
    assert r.participant_count == 1
    assert r.message_count == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    r = e.generate_report(cid, "COLLABORATION", T[5], commit=True)
    assert "APPROVAL" in r.disclaimer


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_include_p106(tmp_path, monkeypatch):
    assert "agent_governance" in ledger.SOURCE_LAYERS
    assert "knowledge_graph" in ledger.SOURCE_LAYERS
    assert "research_operations" in ledger.SOURCE_LAYERS


def test_source_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("arg_agents.jsonl")
    with open(p, "w") as f:
        for i in range(2):
            f.write(json.dumps({"event_id": f"e{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("agent_governance") == 2
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.invite_participant(cid, "a", now=T[3], commit=True)
    e.post_message(cid, "a", "RESULT", "r", now=T[4], commit=True)
    e.add_peer_review(cid, "r", "t", "risk", 0.5, now=T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _collab(e)
    p = sp("rcol_collaborations.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.post_message(cid, "a", "QUESTION", "q1", now=T[3], commit=True)
    e.post_message(cid, "a", "QUESTION", "q2", now=T[4], commit=True)
    p = sp("rcol_messages.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _collab(e)
    p = sp("rcol_collaborations.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    pid = e.invite_participant(cid, "a", now=T[3], commit=True).participant_id
    e.accept_participation(pid, T[4], commit=True)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _collab(e, "a")
    _collab(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.invite_participant(cid, "a", now=T[3], commit=True)
    e.post_message(cid, "a", "RESULT", "r", now=T[4], commit=True)
    assert reference_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.post_message(cid, "a", "RESULT", "r", now=T[4], commit=True)
    assert lineage_integrity()["ok"] is True


def test_reference_detects_orphan_message(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.post_message(cid, "a", "RESULT", "r", now=T[4], commit=True)
    p = sp("rcol_messages.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["collaboration_id"] = "CXB:ghost"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert reference_integrity()["ok"] is False


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.post_message(cid, "a", "SUMMARY", "s", now=T[3], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["COLLABORATE", "DISCUSS", "PROPOSE", "REVIEW", "RECORD"])
def test_allowed_verb(verb):
    assert is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "PROMOTE_MODEL", "CHANGE_PERMISSION",
                                "AUTO_EXECUTE", "AUTO_APPROVE", "APPROVE_FOR_TRADING"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.collaboration_id, ("n",), "CXB:"),
    (M.collab_event_id, ("c", "S", 0), "CXL:"),
    (M.participant_id, ("c", "a"), "CXU:"),
    (M.participation_event_id, ("p", "S", 0), "CXP:"),
    (M.message_id, ("c", "a", 0), "CXM:"),
    (M.proposal_id, ("c", "t"), "CXO:"),
    (M.proposal_event_id, ("p", "S", 0), "CXR:"),
    (M.review_id, ("r", "t", "c", 0), "CXV:"),
    (M.consensus_id, ("c", "t"), "CXG:"),
    (M.consensus_event_id, ("c", "S", 0), "CXS:"),
    (M.conflict_id, ("c", "t", 0), "CXK:"),
    (M.conflict_event_id, ("c", "S", 0), "CXC:"),
    (M.human_review_id, ("c", "s", 0), "CXW:"),
    (M.human_review_event_id, ("h", "S", 0), "CXH:"),
    (M.report_id, ("c", "s", "t"), "CXN:"),
    (M.artifact_id, ("COLLABORATION", "r"), "CXF:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ 조회 ═══════════════
def test_list_collaborations(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _collab(e, "a")
    _collab(e, "b")
    assert len(e.list_collaborations()) == 2


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = _active(e)
    e.invite_participant(cid, "a", now=T[3], commit=True)
    e.post_message(cid, "a", "RESULT", "r", now=T[4], commit=True)
    s = e.summary(T[9])
    assert s.message_count == 1
    assert s.participation_event_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_collab(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_collaboration.__main__ import main
    assert main(["collab", "--name", "c", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["collaboration"]["to_state"] == "CREATED"


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_collaboration.__main__ import main
    main(["collab", "--name", "c", "--commit"])
    cid = json.loads(capsys.readouterr().out)["collaboration"]["collaboration_id"]
    # form + activate via engine not CLI; use messages after activation path — invite works in CREATED? no
    from jarvis.research_collaboration.engine import ResearchCollaborationEngine
    e = ResearchCollaborationEngine()
    e.form_collaboration(cid, "2026-07-24T00:01:00Z", commit=True)
    e.activate_collaboration(cid, "2026-07-24T00:02:00Z", commit=True)
    assert main(["invite", "--collab", cid, "--agent", "a1", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["participant"]["to_state"] == "INVITED"


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_collaboration.__main__ import main
    assert main(["verify"]) == 0


def test_cli_collaborations(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_collaboration.__main__ import main
    main(["collab", "--name", "c", "--commit"])
    capsys.readouterr()
    assert main(["collaborations"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["collaborations"]) == 1


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_collaboration.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_collaboration.__main__ import main
    assert main(["summary"]) == 0


# ═══════════════ 격리 / 불변 ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_collaboration("c", "o", T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "rcol_collaborations.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_collaboration("c", "o", T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"


def test_ten_ledgers():
    assert len(ledger.ALL_LEDGERS) == 10


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rcol_")


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.live_execution", "jarvis.live_trading",
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
    bad = ("trade", "execute", "deploy", "allocate", "promote", "approve_for_trading",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "promote_model",
           "change_permission", "auto_execute", "auto_approve")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    # append-only: 파괴적 원장 변형 API 없음 (remove_participation 은 REMOVED 상태 전이라 append-only)
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def purge_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cid = e.create_collaboration("alpha-team", "discover alpha", T[0], commit=True).collaboration_id
    e.form_collaboration(cid, T[1], commit=True)
    p1 = e.invite_participant(cid, "agentA", "lead", "alpha", "", T[2], commit=True).participant_id
    p2 = e.invite_participant(cid, "agentB", "reviewer", "risk", "", T[3], commit=True).participant_id
    e.activate_collaboration(cid, T[4], commit=True)
    e.accept_participation(p1, T[5], commit=True)
    e.activate_participation(p1, T[6], commit=True)
    e.post_message(cid, "agentA", "HYPOTHESIS", "momentum works", ["kg:1"], {}, T[7], commit=True)
    e.post_message(cid, "agentB", "CRITIQUE", "check robustness", [], {}, T[8], commit=True)
    prid = e.create_proposal(cid, "agentA", "adopt momentum study", T[9], commit=True).proposal_id
    e.submit_proposal(prid, T[10], commit=True)
    e.discuss_proposal(prid, T[11], commit=True)
    e.add_peer_review(cid, "agentB", prid, "robustness", 0.7, "ok", ["sim:1"], T[12], commit=True)
    e.review_proposal(prid, T[13], commit=True)
    cons = e.open_consensus(cid, "adopt momentum", T[14], commit=True).consensus_id
    e.discuss_consensus(cons, {"AGREEMENT": 2, "DISAGREEMENT": 1}, T[15], commit=True)
    e.tentative_consensus(cons, {}, T[16], commit=True)
    e.review_consensus(cons, {}, T[17], commit=True)
    e.record_consensus(cons, {"AGREEMENT": 2, "MINORITY_OPINION": ["agentB partial"]}, T[18],
                       commit=True)
    conf = e.open_conflict(cid, "INTERPRETATION", "differ on threshold", T[19], commit=True).conflict_id
    e.analyze_conflict(conf, T[20], commit=True)
    e.resolve_conflict(conf, "documented both", T[21], commit=True)
    e.document_conflict(conf, "recorded", T[22], commit=True)
    hr = e.request_human_review(cid, "adopt momentum study", T[23], commit=True).human_review_id
    e.assign_human_review(hr, "dr.oversight", T[24], commit=True)
    e.start_human_review(hr, T[25], commit=True)
    e.comment_human_review(hr, "approved for research record only", T[26], commit=True)
    e.close_human_review(hr, T[27], commit=True)
    acc = e.accept_proposal(prid, T[28], commit=True)
    assert acc.to_state == "ACCEPTED"
    assert acc.basis in ("human_review", "consensus")
    e.review_collaboration(cid, T[29], commit=True)
    rep = e.generate_report(cid, "COLLABORATION", T[30], commit=True)
    assert rep.participant_count == 2
    assert rep.proposal_count == 1
    assert rep.consensus_count == 1
    assert rep.is_binding is False
    e.complete_collaboration(cid, T[31], commit=True)
    e.archive_collaboration(cid, T[32], commit=True)
    assert e.collaboration_state(cid) == "ARCHIVED"
    assert verify_chain()["ok"] is True
    assert replay(e, T[33])["deterministic"] is True
