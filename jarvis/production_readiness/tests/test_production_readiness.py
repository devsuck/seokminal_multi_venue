"""P21 production_readiness 테스트 — 후보 불변·체크리스트·요구·리뷰(검토자 필수·자동승인 차단)·
리스크·전환 상태 머신·계보·verify·replay·CLI·보안·금지능력·READ ONLY 상위."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.production_readiness import ledger
from jarvis.production_readiness import models as M
from jarvis.production_readiness.engine import ProductionReadinessEngine
from jarvis.production_readiness.models import (
    CANDIDATE_STATES,
    CHECKLIST_CATEGORIES,
    CHECK_STATUSES,
    FORBIDDEN_VERBS,
    GENESIS,
    REQUIREMENT_TYPES,
    REVIEW_STATES,
    RISK_LEVELS,
    R_APPROVED,
    R_PENDING,
    R_REJECTED,
    R_REQUEST_CHANGE,
    S_ARCHIVED,
    S_CHECKING,
    S_READY_FOR_DEPLOYMENT,
    S_READY_FOR_REVIEW,
    S_REGISTERED,
    S_REVIEWED,
    ApprovalRequired,
    IllegalCandidateTransition,
    IllegalReviewTransition,
    ImmutableCandidateError,
    MissingEvidenceError,
    ReviewerRequired,
    UnknownEntityError,
    can_candidate_transition,
    can_review_transition,
    content_hash,
    is_forbidden_verb,
)
from jarvis.production_readiness.verify import (
    approval_integrity,
    candidate_lifecycle_integrity,
    duplicate_integrity,
    evidence_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    review_lifecycle_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.production_readiness.ledger.state_path", sp)
    return sp


def _eng():
    return ProductionReadinessEngine()


def _cand(e, layer="research_operations", ref="wf1", strat="s1", now=T[0]):
    return e.register_candidate(layer, ref, strat, "m1", "p1", {"a": 1}, now, commit=True).candidate_id


def _checked(e, cand):
    e.create_readiness_check(cand, "research_quality", "PASS", ["ev1"], "", T[1], commit=True)
    e.create_readiness_check(cand, "data_quality", "PASS", ["ev2"], "", T[2], commit=True)


def _approved(e, cand, now0=5):
    """후보를 승인 리뷰까지 진행."""
    _checked(e, cand)
    e.mark_ready_for_review(cand, T[now0], commit=True)
    rev = e.request_review(cand, "deploy", T[now0 + 1], commit=True).review_id
    e.record_review(rev, "dr.human", "APPROVE", "ok", T[now0 + 2], commit=True)
    e.mark_reviewed(cand, T[now0 + 3], commit=True)
    return rev


# ═══════════════ candidate (immutable) ═══════════════
def test_register_candidate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().register_candidate("research_operations", "wf1", "s1", "m1", "p1", {}, T[0],
                                  commit=True)
    assert c.candidate_id.startswith("PDC:")
    assert c.strategy_reference == "s1"


def test_candidate_genesis_registered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    assert e.candidate_state(cand) == S_REGISTERED


def test_candidate_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_candidate("l", "r", "s1", now=T[0], commit=True)
    with pytest.raises(ImmutableCandidateError):
        e.register_candidate("l", "r", "s2", now=T[1], commit=True)


def test_candidate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_candidate("l", "r", "s", now=T[0], commit=True).candidate_id
    b = e.register_candidate("l", "r", "s", now=T[1], commit=True).candidate_id
    assert a == b
    assert len(ledger.read_candidates()) == 1


def test_candidate_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_candidate("l", "r", now=T[0], commit=False)
    assert ledger.read_candidates() == []


def test_candidate_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cand(e)
    assert any(a["artifact_type"] == "CANDIDATE" for a in ledger.read_artifacts())


def test_candidate_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().register_candidate("l", "r", now=T[0], commit=True)
    with pytest.raises(Exception):
        c.strategy_reference = "x"


# ═══════════════ readiness check (evidence required) ═══════════════
def test_check_requires_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    with pytest.raises(MissingEvidenceError):
        e.create_readiness_check(cand, "research_quality", "PASS", [], "", T[1], commit=True)


def test_check_transitions_checking(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    e.create_readiness_check(cand, "research_quality", "PASS", ["ev"], "", T[1], commit=True)
    assert e.candidate_state(cand) == S_CHECKING


def test_check_warning_status(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    c = e.create_readiness_check(cand, "risk_validation", "WARNING", ["ev"], "", T[1], commit=True)
    assert c.status == "WARNING"


def test_check_failed_status(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    c = e.create_readiness_check(cand, "model_validation", "FAILED", ["ev"], "", T[1], commit=True)
    assert c.status == "FAILED"


def test_check_bad_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    with pytest.raises(ValueError):
        e.create_readiness_check(cand, "nope", "PASS", ["ev"], "", T[1], commit=True)


def test_check_bad_status(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    with pytest.raises(ValueError):
        e.create_readiness_check(cand, "research_quality", "MAYBE", ["ev"], "", T[1], commit=True)


def test_check_evidence_required_flag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    c = e.create_readiness_check(cand, "research_quality", "PASS", ["ev"], "", T[1], commit=True)
    assert c.evidence_required is True


@pytest.mark.parametrize("cat", CHECKLIST_CATEGORIES)
def test_checklist_categories(cat):
    assert cat in CHECKLIST_CATEGORIES


def test_nine_categories():
    assert len(CHECKLIST_CATEGORIES) == 9


@pytest.mark.parametrize("st", CHECK_STATUSES)
def test_check_statuses(st):
    assert st in CHECK_STATUSES


# ═══════════════ requirements ═══════════════
def test_evaluate_requirement(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    r = e.evaluate_requirements(cand, "minimum_oos_result", "0.5", "0.7", True, "", T[1],
                                commit=True)
    assert r.requirement_id.startswith("PDQ:")
    assert r.met is True


def test_requirement_unmet(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    r = e.evaluate_requirements(cand, "maximum_drawdown_limit", "0.2", "0.35", False, "", T[1],
                                commit=True)
    assert r.met is False


def test_requirement_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    with pytest.raises(ValueError):
        e.evaluate_requirements(cand, "nope", "x", "y", True, "", T[1], commit=True)


@pytest.mark.parametrize("rt", REQUIREMENT_TYPES)
def test_requirement_types(rt):
    assert rt in REQUIREMENT_TYPES


# ═══════════════ candidate state machine ═══════════════
def test_full_candidate_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _approved(e, cand)
    e.mark_ready_for_deployment(cand, T[10], commit=True)
    assert e.candidate_state(cand) == S_READY_FOR_DEPLOYMENT
    e.archive_candidate(cand, T[11], commit=True)
    assert e.candidate_state(cand) == S_ARCHIVED


def test_ready_for_review_requires_checks(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    with pytest.raises(IllegalCandidateTransition):
        e.mark_ready_for_review(cand, T[1], commit=True)


def test_ready_for_review_blocked_by_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    e.create_readiness_check(cand, "model_validation", "FAILED", ["ev"], "", T[1], commit=True)
    with pytest.raises(IllegalCandidateTransition):
        e.mark_ready_for_review(cand, T[2], commit=True)


def test_no_skip_registered_to_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    with pytest.raises(IllegalCandidateTransition):
        e.create_transition_record(cand, S_REVIEWED, "", T[1], commit=True)


def test_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _approved(e, cand)
    e.mark_ready_for_deployment(cand, T[10], commit=True)
    e.archive_candidate(cand, T[11], commit=True)
    with pytest.raises(IllegalCandidateTransition):
        e.create_transition_record(cand, S_CHECKING, "", T[12], commit=True)


def test_transition_unknown_candidate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().create_transition_record("PDC:nope", S_CHECKING, "", T[1], commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (S_REGISTERED, S_CHECKING, True), (S_REGISTERED, S_READY_FOR_REVIEW, False),
    (S_CHECKING, S_READY_FOR_REVIEW, True), (S_READY_FOR_REVIEW, S_REVIEWED, True),
    (S_REVIEWED, S_READY_FOR_DEPLOYMENT, True), (S_REVIEWED, S_CHECKING, True),
    (S_READY_FOR_DEPLOYMENT, S_ARCHIVED, True), (S_ARCHIVED, S_CHECKING, False),
    (S_REGISTERED, S_READY_FOR_DEPLOYMENT, False),
])
def test_candidate_transition_matrix(frm, to, ok):
    assert can_candidate_transition(frm, to) is ok


@pytest.mark.parametrize("s", CANDIDATE_STATES)
def test_candidate_states(s):
    assert s in CANDIDATE_STATES


# ═══════════════ review (reviewer required, no auto approval) ═══════════════
def test_request_review_pending(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    r = e.request_review(cand, "deploy", T[1], commit=True)
    assert r.review_id.startswith("PDV:")
    assert r.to_state == R_PENDING
    assert r.is_automatic is False


def test_review_requires_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    rev = e.request_review(cand, "deploy", T[1], commit=True).review_id
    with pytest.raises(ReviewerRequired):
        e.record_review(rev, "", "APPROVE", "", T[2], commit=True)


def test_review_approve(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    rev = e.request_review(cand, "deploy", T[1], commit=True).review_id
    ev = e.record_review(rev, "dr.jane", "APPROVE", "ok", T[2], commit=True)
    assert ev.to_state == R_APPROVED
    assert ev.reviewer_id == "dr.jane"
    assert ev.is_automatic is False


def test_review_reject(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    rev = e.request_review(cand, "deploy", T[1], commit=True).review_id
    ev = e.record_review(rev, "dr.jane", "REJECT", "no", T[2], commit=True)
    assert ev.to_state == R_REJECTED


def test_review_request_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    rev = e.request_review(cand, "deploy", T[1], commit=True).review_id
    ev = e.record_review(rev, "dr.jane", "REQUEST_CHANGE", "fix", T[2], commit=True)
    assert ev.to_state == R_REQUEST_CHANGE


def test_review_bad_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    rev = e.request_review(cand, "deploy", T[1], commit=True).review_id
    with pytest.raises(ValueError):
        e.record_review(rev, "dr.jane", "MAYBE", "", T[2], commit=True)


def test_review_double_decision_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    rev = e.request_review(cand, "deploy", T[1], commit=True).review_id
    e.record_review(rev, "dr.jane", "APPROVE", "", T[2], commit=True)
    with pytest.raises(IllegalReviewTransition):
        e.record_review(rev, "dr.jane", "REJECT", "", T[3], commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (R_PENDING, R_APPROVED, True), (R_PENDING, R_REJECTED, True), (R_PENDING, R_REQUEST_CHANGE, True),
    (R_APPROVED, R_REJECTED, False), (R_REJECTED, R_APPROVED, False),
])
def test_review_transition_matrix(frm, to, ok):
    assert can_review_transition(frm, to) is ok


@pytest.mark.parametrize("s", REVIEW_STATES)
def test_review_states(s):
    assert s in REVIEW_STATES


# ═══════════════ deployment gate (approval required, no deploy) ═══════════════
def test_ready_for_deployment_requires_approval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _checked(e, cand)
    e.mark_ready_for_review(cand, T[5], commit=True)
    rev = e.request_review(cand, "deploy", T[6], commit=True).review_id
    e.record_review(rev, "dr.jane", "REJECT", "", T[7], commit=True)  # 거부
    e.mark_reviewed(cand, T[8], commit=True)
    # 승인 없음 → READY_FOR_DEPLOYMENT 불가
    with pytest.raises(ApprovalRequired):
        e.mark_ready_for_deployment(cand, T[9], commit=True)


def test_ready_for_deployment_with_approval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _approved(e, cand)
    tr = e.mark_ready_for_deployment(cand, T[10], commit=True)
    assert tr.to_state == S_READY_FOR_DEPLOYMENT
    # 배포 아님 — 상태 표기일 뿐
    assert e.candidate_state(cand) == S_READY_FOR_DEPLOYMENT


def test_report_deployed_false(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _approved(e, cand)
    e.mark_ready_for_deployment(cand, T[10], commit=True)
    r = e.generate_readiness_report(cand, "CANDIDATE", T[11], commit=True)
    assert r.deployed is False
    assert r.is_binding is False
    assert r.candidate_state == S_READY_FOR_DEPLOYMENT


# ═══════════════ risk ═══════════════
def test_assess_risk(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    r = e.assess_transition_risk(cand, "MEDIUM", ["cost", "regime"], "moderate", T[1], commit=True)
    assert r.risk_id.startswith("PDS:")
    assert r.level == "MEDIUM"
    assert r.is_binding is False


def test_risk_bad_level(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    with pytest.raises(ValueError):
        e.assess_transition_risk(cand, "NUCLEAR", now=T[1], commit=True)


@pytest.mark.parametrize("lvl", RISK_LEVELS)
def test_risk_levels(lvl):
    assert lvl in RISK_LEVELS


# ═══════════════ report ═══════════════
def test_report_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    e.create_readiness_check(cand, "research_quality", "PASS", ["ev"], "", T[1], commit=True)
    e.create_readiness_check(cand, "risk_validation", "WARNING", ["ev"], "", T[2], commit=True)
    e.evaluate_requirements(cand, "minimum_oos_result", "0.5", "0.7", True, "", T[3], commit=True)
    r = e.generate_readiness_report(cand, "CANDIDATE", T[4], commit=True)
    assert r.check_summary.get("PASS") == 1
    assert r.check_summary.get("WARNING") == 1
    assert r.requirement_summary["met"] == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    r = e.generate_readiness_report(cand, "CANDIDATE", T[1], commit=True)
    assert "DEPLOYED" in r.disclaimer


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers(tmp_path, monkeypatch):
    for k in ("data_governance", "model_governance", "simulation", "research_operations",
              "continuous_learning"):
        assert k in ledger.SOURCE_LAYERS


def test_source_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("mg_models.jsonl")
    with open(p, "w") as f:
        for i in range(2):
            f.write(json.dumps({"model_hash": f"m{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("model_governance") == 2
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _approved(e, cand)
    e.assess_transition_risk(cand, "LOW", ["ok"], "", T[9], commit=True)
    e.mark_ready_for_deployment(cand, T[10], commit=True)
    e.generate_readiness_report(cand, "CANDIDATE", T[11], commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] > 0


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _cand(e)
    p = sp("pd_candidates.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["strategy_reference"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    e.create_readiness_check(cand, "research_quality", "PASS", ["ev"], "", T[1], commit=True)
    e.create_readiness_check(cand, "data_quality", "PASS", ["ev"], "", T[2], commit=True)
    p = sp("pd_readiness_checks.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _cand(e)
    p = sp("pd_candidates.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_candidate_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _checked(e, cand)
    assert candidate_lifecycle_integrity()["ok"] is True


def test_review_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    rev = e.request_review(cand, "s", T[1], commit=True).review_id
    e.record_review(rev, "r", "APPROVE", "", T[2], commit=True)
    assert review_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cand(e, ref="a")
    _cand(e, ref="b")
    assert duplicate_integrity()["ok"] is True


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _checked(e, cand)
    assert reference_integrity()["ok"] is True


def test_evidence_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _checked(e, cand)
    assert evidence_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cand(e)
    assert lineage_integrity()["ok"] is True


# ═══════════════ approval integrity: unauthorized / automatic approval ═══════════════
def test_approval_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _approved(e, cand)
    e.mark_ready_for_deployment(cand, T[10], commit=True)
    assert approval_integrity()["ok"] is True


def test_approval_integrity_detects_automatic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    rev = e.request_review(cand, "s", T[1], commit=True).review_id
    e.record_review(rev, "r", "APPROVE", "", T[2], commit=True)
    p = sp("pd_reviews.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[-1]["is_automatic"] = True  # 자동 승인 위조
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert approval_integrity()["ok"] is False
    assert any("automatic_approval" in i for i in approval_integrity()["issues"])


def test_approval_integrity_detects_unauthorized(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    rev = e.request_review(cand, "s", T[1], commit=True).review_id
    e.record_review(rev, "r", "APPROVE", "", T[2], commit=True)
    p = sp("pd_reviews.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[-1]["reviewer_id"] = ""  # 검토자 제거(비인가 승인)
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert approval_integrity()["ok"] is False
    assert any("unauthorized_approval" in i for i in approval_integrity()["issues"])


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _checked(e, cand)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["REGISTER", "CHECK", "REVIEW", "ASSESS", "REPORT", "VERIFY"])
def test_allowed_verb(verb):
    assert is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "ACTIVATE_LIVE", "PROMOTE_MODEL",
                                "CHANGE_PERMISSION", "ENABLE_EXECUTION"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.candidate_id, ("l", "r"), "PDC:"),
    (M.transition_id, ("c", "S", 0), "PDT:"),
    (M.check_id, ("c", "cat", 0), "PDK:"),
    (M.requirement_id, ("c", "t", 0), "PDQ:"),
    (M.review_id, ("c", "s"), "PDV:"),
    (M.review_event_id, ("r", "S", 0), "PDW:"),
    (M.risk_id, ("c", 0), "PDS:"),
    (M.report_id, ("c", "s", "t"), "PDG:"),
    (M.artifact_id, ("CANDIDATE", "r"), "PDA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ 조회 ═══════════════
def test_list_candidates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cand(e, ref="a")
    _cand(e, ref="b")
    assert len(e.list_candidates()) == 2


def test_candidates_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    e.create_readiness_check(cand, "research_quality", "PASS", ["ev"], "", T[1], commit=True)
    assert cand in e.candidates_in_state(S_CHECKING)


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = _cand(e)
    _checked(e, cand)
    s = e.summary(T[9])
    assert s.candidate_count == 1
    assert s.check_count == 2


# ═══════════════ CLI ═══════════════
def test_cli_candidate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.production_readiness.__main__ import main
    assert main(["candidate", "--layer", "l", "--ref", "r", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["candidate"]["candidate_id"].startswith("PDC:")


def test_cli_check(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.production_readiness.__main__ import main
    main(["candidate", "--layer", "l", "--ref", "r", "--commit"])
    cand = json.loads(capsys.readouterr().out)["candidate"]["candidate_id"]
    assert main(["check", "--candidate", cand, "--category", "research_quality",
                 "--status", "PASS", "--evidence", "ev1", "--commit"]) == 0


def test_cli_review_reviewer_required(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.production_readiness.__main__ import main
    main(["candidate", "--layer", "l", "--ref", "r", "--commit"])
    cand = json.loads(capsys.readouterr().out)["candidate"]["candidate_id"]
    main(["review", "--candidate", cand, "--subject", "deploy", "--commit"])
    capsys.readouterr()
    # 검토자 없이 결정 시도 → 예외
    with pytest.raises(ReviewerRequired):
        main(["review", "--candidate", cand, "--subject", "deploy", "--decision", "APPROVE",
              "--commit"])


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.production_readiness.__main__ import main
    assert main(["verify"]) == 0


def test_cli_candidates(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.production_readiness.__main__ import main
    main(["candidate", "--layer", "l", "--ref", "r", "--commit"])
    capsys.readouterr()
    assert main(["candidates"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["candidates"]) == 1


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.production_readiness.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.production_readiness.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_candidate("l", "r", now=T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "pd_candidates.jsonl"))


def test_eight_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("pd_")


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.live_execution", "jarvis.live_trading", "jarvis.portfolio_manager",
    "jarvis.risk_engine", "jarvis.permission_manager",
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
    bad = ("deploy", "activate", "execute", "trade", "allocate", "execute_trade", "place_order",
           "allocate_capital", "deploy_strategy", "activate_live", "promote_model",
           "change_permission", "enable_execution")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def update_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cand = e.register_candidate("research_operations", "wf-momentum", "strat:mom", "model:xgb",
                                "port:kospi", {"sharpe": 1.3}, T[0], commit=True).candidate_id
    # 준비성 체크 9범주
    for i, cat in enumerate(M.CHECKLIST_CATEGORIES):
        status = "WARNING" if cat == "risk_validation" else "PASS"
        e.create_readiness_check(cand, cat, status, [f"evidence:{cat}"], "", T[1 + i], commit=True)
    # 요구사항 평가
    e.evaluate_requirements(cand, "minimum_oos_result", "0.5", "0.72", True, "", T[11], commit=True)
    e.evaluate_requirements(cand, "human_review_required", "yes", "pending", False, "", T[12],
                            commit=True)
    # 리스크
    e.assess_transition_risk(cand, "MEDIUM", ["cost"], "acceptable", T[13], commit=True)
    # 검토 준비
    e.mark_ready_for_review(cand, T[14], commit=True)
    assert e.candidate_state(cand) == S_READY_FOR_REVIEW
    # 사람 리뷰(승인) — 검토자 필수
    rev = e.request_review(cand, "production deploy readiness", T[15], commit=True).review_id
    e.record_review(rev, "dr.oversight", "APPROVE", "meets research criteria", T[16], commit=True)
    e.mark_reviewed(cand, T[17], commit=True)
    # 승인된 리뷰가 있어야 READY_FOR_DEPLOYMENT
    e.mark_ready_for_deployment(cand, T[18], commit=True)
    assert e.candidate_state(cand) == S_READY_FOR_DEPLOYMENT
    # 리포트 — 배포되지 않음
    r = e.generate_readiness_report(cand, "CANDIDATE", T[19], commit=True)
    assert r.deployed is False
    assert r.review_decision == "APPROVED"
    assert r.check_summary.get("PASS") == 8
    assert r.check_summary.get("WARNING") == 1
    e.archive_candidate(cand, T[20], commit=True)
    assert e.candidate_state(cand) == S_ARCHIVED
    res = verify_chain()
    assert res["ok"] is True
    assert res["approval"]["ok"] is True
    assert replay(e, T[21])["deterministic"] is True
