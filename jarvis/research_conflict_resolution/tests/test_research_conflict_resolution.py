"""P11.9 Research Conflict Resolution 테스트. **연구 충돌 분석·해소 — 리뷰·분석 전용.**

레지스트리·충돌 등록·생애주기(DETECTED→ANALYZING→DISCUSSING→RESOLVED→ARCHIVED)·주장(불변·보존)·증거(READ ONLY·
불변)·에이전트 포지션(불변)·주장 비교(결정적)·해소 세션·해소 결과(4유형·합의 결정성)·소수의견 보존·리포트·
아티팩트 계보·verify(체인/변조/중복/생애주기/합의결정성/참조/계보/소수보존)·replay·CLI·보안(금지import·실행/승인/
수정 없음·삭제 API 없음·불변·CONFLICT≠EXECUTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_conflict_resolution import ledger
from jarvis.research_conflict_resolution import models as M
from jarvis.research_conflict_resolution.engine import ResearchConflictResolutionEngine
from jarvis.research_conflict_resolution.models import (
    C_ANALYZING,
    C_ARCHIVED,
    C_DETECTED,
    C_DISCUSSING,
    C_RESOLVED,
    EV_BACKTEST,
    EV_METRIC,
    R_CONSENSUS,
    R_EVIDENCE_SUPERIOR,
    R_MAJORITY,
    R_UNRESOLVED,
    ConflictClosedError,
    IllegalConflictTransition,
    ImmutableClaimError,
    ImmutableOutcomeError,
    ImmutablePositionError,
    InvalidEvidenceType,
    InvalidResolutionType,
    UnknownClaimError,
    UnknownConflictError,
    UnknownRegistryError,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(40)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_conflict_resolution.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchConflictResolutionEngine()


def _reg(e, name="conflict_board", now=T[0]):
    return e.register_registry(name, "resolve disagreements", now, commit=True).registry_id


def _conflict(e, reg=None, subject="momentum robustness", now=T[0]):
    if reg is None:
        reg = _reg(e, now=now)
    return e.register_conflict(reg, subject, "agents disagree", now, commit=True).conflict_id


def _analyzing(e):
    reg = _reg(e)
    c = e.register_conflict(reg, "subj", "d", T[0], commit=True).conflict_id
    e.start_analysis(c, T[1], commit=True)
    return reg, c


def _with_claims(e):
    """ANALYZING 충돌 + 2 주장 + 3 포지션 (2 support claim A, 1 support B)."""
    reg, c = _analyzing(e)
    a = e.add_claim(c, "alpha_agent", "momentum robust", "IR>1", T[2], commit=True).claim_id
    b = e.add_claim(c, "risk_agent", "momentum overfit", "OOS weak", T[3], commit=True).claim_id
    e.record_agent_position(c, "alpha_agent", a, "supports A", T[4], commit=True)
    e.record_agent_position(c, "sim_agent", a, "supports A", T[5], commit=True)
    e.record_agent_position(c, "risk_agent", b, "supports B", T[6], commit=True)
    return reg, c, a, b


# ══════════════ registry / conflict ══════════════
def test_registry_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().register_registry("board", "m", T[0], commit=True)
    assert r.registry_id.startswith("CRG:")


def test_registry_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg(e)
    _reg(e, now=T[1])
    assert len(ledger.read_registry()) == 1


def test_conflict_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _conflict(e)
    assert e.current_state(c) == C_DETECTED


def test_conflict_unknown_registry(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRegistryError):
        _eng().register_conflict("CRG:ghost", "s", "", T[0], commit=True)


def test_conflict_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    a = e.register_conflict(reg, "s", "d", T[0], commit=False)
    b = e.register_conflict(reg, "s", "d2", T[1], commit=False)
    assert a.conflict_id == b.conflict_id


def test_conflict_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    e.register_conflict(reg, "s", "d", T[0], commit=True)
    e.register_conflict(reg, "s", "d", T[1], commit=True)
    assert len(ledger.conflict_ids()) == 1


def test_conflict_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _conflict(e)
    assert any(a["artifact_type"] == "CONFLICT" for a in ledger.read_artifacts())


# ══════════════ lifecycle ══════════════
def test_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "facilitator", "analysis", T[10], commit=True)
    assert e.current_state(c) == C_DISCUSSING
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "A wins", T[11], commit=True)
    assert e.current_state(c) == C_RESOLVED
    e.archive_conflict(c, T[12], commit=True)
    assert e.current_state(c) == C_ARCHIVED


def test_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _conflict(e)
    with pytest.raises(IllegalConflictTransition):
        e.archive_conflict(c, T[1], commit=True)  # DETECTED->ARCHIVED 불가


def test_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    e.archive_conflict(c, T[12], commit=True)
    with pytest.raises(IllegalConflictTransition):
        e.start_analysis(c, T[13], commit=True)


def test_conflict_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    c = e.register_conflict(reg, "SubjectX", "descY", T[0], commit=True).conflict_id
    m = e.conflict_meta(c)
    assert m["subject"] == "SubjectX"
    assert m["registry_id"] == reg


def test_five_states():
    assert len(M.CONFLICT_STATES) == 5


# ══════════════ add_claim (preservation) ══════════════
def test_add_claim(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "alpha_agent", "robust", "IR>1", T[2], commit=True)
    assert cl.claim_id.startswith("CFM:")
    assert cl.agent == "alpha_agent"


def test_claim_preserves_identity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "alpha_agent", "robust", "reason", T[2], commit=True)
    stored = ledger.get_claim(cl.claim_id)
    assert stored["agent"] == "alpha_agent"
    assert stored["rationale"] == "reason"


def test_claim_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    e.add_claim(c, "a", "concl", "r1", T[2], commit=True)
    with pytest.raises(ImmutableClaimError):
        e.add_claim(c, "a", "concl", "r2", T[3], commit=True)


def test_claim_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    e.add_claim(c, "a", "concl", "r", T[2], commit=True)
    e.add_claim(c, "a", "concl", "r", T[3], commit=True)
    assert len(ledger.conflict_claims(c)) == 1


def test_claim_multiple_agents(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    e.add_claim(c, "a", "robust", "", T[2], commit=True)
    e.add_claim(c, "b", "overfit", "", T[3], commit=True)
    assert len(ledger.conflict_claims(c)) == 2


def test_claim_on_resolved_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    with pytest.raises(ConflictClosedError):
        e.add_claim(c, "late_agent", "new claim", "", T[12], commit=True)


# ══════════════ attach_evidence ══════════════
def test_attach_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "robust", "", T[2], commit=True).claim_id
    ev = e.attach_evidence(cl, "research_reviewer", "rvw1", EV_REVIEW := "REVIEW", "high IR", T[3],
                           commit=True)
    assert ev.evidence_id.startswith("CFV:")
    assert ev.read_only is True


def test_evidence_unknown_claim(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownClaimError):
        _eng().attach_evidence("CFM:ghost", "l", "r", EV_METRIC, "", T[0], commit=True)


def test_evidence_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    with pytest.raises(InvalidEvidenceType):
        e.attach_evidence(cl, "l", "r", "BOGUS", "", T[3], commit=True)


def test_evidence_verify_ref(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rvw_reviews.jsonl"), "w") as f:
        f.write(json.dumps({"review_id": "rvw1"}) + "\n")
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    ev = e.attach_evidence(cl, "research_reviewer", "rvw1", "REVIEW", "", T[3], commit=True,
                           verify_ref=True)
    assert ev.ref == "rvw1"


def test_evidence_verify_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    with pytest.raises(UnknownClaimError):
        e.attach_evidence(cl, "research_reviewer", "ghost", "REVIEW", "", T[3], commit=True,
                          verify_ref=True)


def test_evidence_source_never_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rvw_reviews.jsonl"), "w") as f:
        f.write(json.dumps({"review_id": "rvw1"}) + "\n")
    before = open(sp("rvw_reviews.jsonl")).read()
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    e.attach_evidence(cl, "research_reviewer", "rvw1", "REVIEW", "", T[3], commit=True,
                      verify_ref=True)
    assert open(sp("rvw_reviews.jsonl")).read() == before


@pytest.mark.parametrize("etype", list(M.EVIDENCE_TYPES))
def test_evidence_all_types(tmp_path, monkeypatch, etype):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    ev = e.attach_evidence(cl, "l", f"r_{etype}", etype, "", T[3], commit=True)
    assert ev.evidence_type == etype


# ══════════════ record_agent_position ══════════════
def test_position(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    p = e.record_agent_position(c, "b", cl, "agrees", T[3], commit=True)
    assert p.position_id.startswith("CFP:")
    assert p.backed_claim == cl


def test_position_unknown_claim(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    with pytest.raises(UnknownClaimError):
        e.record_agent_position(c, "b", "CFM:ghost", "", T[3], commit=True)


def test_position_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    a = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    b = e.add_claim(c, "b", "y", "", T[3], commit=True).claim_id
    e.record_agent_position(c, "z", a, "", T[4], commit=True)
    with pytest.raises(ImmutablePositionError):
        e.record_agent_position(c, "z", b, "", T[5], commit=True)


# ══════════════ compare_claims (deterministic) ══════════════
def test_compare_majority(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    res = e.compare_claims(c)
    assert res["support_tally"][a] == 2
    assert res["support_tally"][b] == 1
    assert res["suggested_type"] == R_MAJORITY
    assert res["leading_claim"] == a


def test_compare_consensus(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    a = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    e.add_claim(c, "b", "y", "", T[3], commit=True)
    e.record_agent_position(c, "a", a, "", T[4], commit=True)
    e.record_agent_position(c, "b", a, "", T[5], commit=True)
    res = e.compare_claims(c)
    assert res["suggested_type"] == R_CONSENSUS


def test_compare_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    assert e.compare_claims(c) == e.compare_claims(c)


def test_derive_resolution_pure():
    assert M.derive_resolution({"a": 2}, {})[0] == R_CONSENSUS
    assert M.derive_resolution({"a": 2, "b": 1}, {})[0] == R_MAJORITY
    assert M.derive_resolution({"a": 1, "b": 1}, {"a": 3, "b": 1})[0] == R_EVIDENCE_SUPERIOR
    assert M.derive_resolution({"a": 1, "b": 1}, {"a": 1, "b": 1})[0] == R_UNRESOLVED
    assert M.derive_resolution({}, {})[0] == R_UNRESOLVED


def test_compare_evidence_superior(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    a = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    b = e.add_claim(c, "b", "y", "", T[3], commit=True).claim_id
    e.record_agent_position(c, "a", a, "", T[4], commit=True)
    e.record_agent_position(c, "b", b, "", T[5], commit=True)  # 1-1 tie
    e.attach_evidence(a, "l", "r1", EV_METRIC, "", T[6], commit=True)
    e.attach_evidence(a, "l", "r2", EV_BACKTEST, "", T[7], commit=True)  # a has 2 evidence
    res = e.compare_claims(c)
    assert res["suggested_type"] == R_EVIDENCE_SUPERIOR
    assert res["leading_claim"] == a


# ══════════════ start_resolution / record_resolution ══════════════
def test_start_resolution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    s = e.start_resolution(c, "fac", "analysis", T[10], commit=True)
    assert s.session_id.startswith("CFS:")
    assert e.current_state(c) == C_DISCUSSING


def test_record_resolution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    o = e.record_resolution(c, sess, R_MAJORITY, a, "A wins", T[11], commit=True)
    assert o.resolution_id.startswith("CFO:")
    assert o.resolution_type == R_MAJORITY
    assert o.computed_type == R_MAJORITY
    assert e.current_state(c) == C_RESOLVED


def test_resolution_records_consensus(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    ks = ledger.read_consensus()
    assert len(ks) == 1
    assert ks[0]["computed_type"] == R_MAJORITY


def test_resolution_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    with pytest.raises(InvalidResolutionType):
        e.record_resolution(c, sess, "MAGIC", a, "", T[11], commit=True)


def test_resolution_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    # 재-resolve 시 상태가 RESOLVED 라 다시 호출해도 outcome 불변; type 변경 시 오류
    with pytest.raises(ImmutableOutcomeError):
        e.record_resolution(c, sess, R_CONSENSUS, a, "", T[12], commit=True)


def test_four_resolution_types():
    assert len(M.RESOLUTION_TYPES) == 4


# ══════════════ minority preservation ══════════════
def test_preserve_minority_view(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    m = e.preserve_minority_view(c, "risk_agent", "still overfit", b, T[10], commit=True)
    assert m.minority_id.startswith("CFN:")


def test_preserve_all_minority(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    ms = e.preserve_all_minority(c, a, T[10], commit=True)
    assert len(ms) == 1  # risk_agent backed b (loser)
    assert ms[0].agent == "risk_agent"


def test_minority_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.preserve_minority_view(c, "risk_agent", "op1", b, T[10], commit=True)
    with pytest.raises(Exception):
        e.preserve_minority_view(c, "risk_agent", "op2", b, T[11], commit=True)


def test_minority_preservation_verify(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_conflict_resolution.verify import minority_preservation
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    assert minority_preservation()["ok"] is False  # 미보존
    e.preserve_all_minority(c, a, T[12], commit=True)
    assert minority_preservation()["ok"] is True


# ══════════════ generate_report ══════════════
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    r = e.generate_report(c, "CONFLICT", T[10], commit=True)
    assert r.report_id.startswith("CFR:")
    assert r.claim_count == 2
    assert r.position_count == 3
    assert r.is_binding is False


def test_report_after_resolution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    r = e.generate_report(c, "CONFLICT", T[12], commit=True)
    assert r.resolution_type == R_MAJORITY
    assert r.winning_claim == a


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    x = e.generate_report(c, "CONFLICT", T[10], commit=False)
    y = e.generate_report(c, "CONFLICT", T[10], commit=False)
    assert x.to_dict() == y.to_dict()


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _conflict(e)
    r = e.generate_report(c, "CONFLICT", T[1], commit=True)
    assert "CONFLICT ≠ EXECUTION" in r.disclaimer


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_conflict_resolution.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_full_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_conflict_resolution.verify import verify_chain
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.attach_evidence(a, "l", "r1", EV_METRIC, "", T[7], commit=True)
    e.start_resolution(c, "fac", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "A wins", T[11], commit=True)
    e.preserve_all_minority(c, a, T[12], commit=True)
    e.archive_conflict(c, T[13], commit=True)
    e.generate_report(c, "CONFLICT", T[14], commit=True)
    res = verify_chain(check_minority=True)
    assert res["ok"] is True
    assert res["lifecycle"]["ok"]
    assert res["determinism"]["ok"]
    assert res["reference"]["ok"]
    assert res["lineage"]["ok"]
    assert res["minority"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    e.add_claim(c, "a", "x", "", T[2], commit=True)
    fp = sp("crf_claims.jsonl")
    rows = [json.loads(x) for x in open(fp)]
    rows[0]["conclusion"] = "TAMPERED"
    with open(fp, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_conflict_resolution.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_verify_determinism_detects_forged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    fp = sp("crf_consensus.jsonl")
    rows = [json.loads(x) for x in open(fp)]
    rows[0]["computed_type"] = "CONSENSUS"
    rows[0]["record_hash"] = M.content_hash(rows[0])
    with open(fp, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_conflict_resolution.verify import consensus_determinism
    assert consensus_determinism()["ok"] is False


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_conflict_resolution.verify import replay
    e = _eng()
    _with_claims(e)
    assert replay(e, T[10])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    s = e.summary(T[10])
    assert s.claim_count == 2
    assert s.position_count == 3


# ══════════════ 보안 / 불변식 ══════════════
def test_no_forbidden_imports():
    import ast
    fp = ("execution", "broker", "portfolio", "risk", "permission", "deployment", "live",
          "order", "capital_allocation", "live_trading", "risk_controller", "portfolio_execution")
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
                for f in fp:
                    assert not (sub == f or sub.startswith(f)), (fn, m)


def test_engine_no_execution_methods():
    e = ResearchConflictResolutionEngine()
    for bad in ("execute", "trade", "deploy", "allocate", "approve_for_trading", "modify_strategy",
                "modify_model", "change_permission", "change_config", "approve", "override"):
        assert not hasattr(e, bad), bad


def test_no_execution_verbs_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def execute", "def trade", "def deploy", "def allocate",
                    "def approve_for_trading", "def modify_strategy", "def modify_model",
                    "def change_permission", "def change_config", "def override"):
            assert bad not in src, (fn, bad)


def test_forbidden_verbs_defined():
    for v in ("EXECUTE", "TRADE", "DEPLOY", "APPROVE_FOR_TRADING", "MODIFY_STRATEGY",
              "MODIFY_MODEL", "CHANGE_PERMISSION", "CHANGE_CONFIG"):
        assert M.is_forbidden_verb(v) is True
    assert M.is_forbidden_verb("ANALYZE") is False


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
    from jarvis.research_conflict_resolution.engine import _DISCLAIMER
    assert "CONFLICT ≠ EXECUTION" in _DISCLAIMER
    assert "RESOLUTION ≠ APPROVAL" in _DISCLAIMER


def test_all_evidence_read_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    e.attach_evidence(cl, "l", "r", EV_METRIC, "", T[3], commit=True)
    for ev in ledger.read_evidence():
        assert ev["read_only"] is True


def test_all_reports_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _conflict(e)
    e.generate_report(c, "CONFLICT", T[1], commit=True)
    for r in ledger.read_reports():
        assert r["is_binding"] is False


def test_records_frozen():
    r = M.ClaimRecord(claim_id="CFM:x", conflict_id="CFC:c", agent="a", conclusion="c",
                      rationale="", created_at=T[0])
    with pytest.raises(Exception):
        r.conclusion = "z"  # type: ignore


def test_only_crf_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.attach_evidence(a, "l", "r", EV_METRIC, "", T[7], commit=True)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    e.preserve_all_minority(c, a, T[12], commit=True)
    e.generate_report(c, "CONFLICT", T[13], commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("crf_"), fn


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.registry_id("n")[:4], M.conflict_id("r", "s")[:4],
           M.conflict_event_id("c", "s", 0)[:4], M.claim_id("c", "a", "x")[:4],
           M.evidence_id("cl", "l", "r")[:4], M.position_id("c", "a")[:4],
           M.session_id("c", 0)[:4], M.resolution_id("c", "s")[:4], M.minority_id("c", "a")[:4],
           M.consensus_id("c", "s")[:4], M.report_id("c", "s", T[0])[:4],
           M.artifact_id("t", "r")[:4]}
    assert len(ids) == 12


def test_eleven_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 11
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 11
    assert all(f.startswith("crf_") for f in fns)


def test_seven_evidence_types():
    assert len(M.EVIDENCE_TYPES) == 7


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b")]) == []
    cyc = M.detect_cycle([("a", "b"), ("b", "a")])
    assert cyc and cyc[0] == cyc[-1]


def test_can_transition_pure():
    assert M.can_transition(C_DETECTED, C_ANALYZING) is True
    assert M.can_transition(C_DETECTED, C_RESOLVED) is False


def test_list_conflicts_and_claims(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    assert c in e.list_conflicts(reg)
    assert a in e.claims_of(c)


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (C_DETECTED, C_ANALYZING, True), (C_ANALYZING, C_DISCUSSING, True),
    (C_DISCUSSING, C_RESOLVED, True), (C_DISCUSSING, C_ANALYZING, True),
    (C_RESOLVED, C_ARCHIVED, True), (C_DETECTED, C_DISCUSSING, False),
    (C_ANALYZING, C_RESOLVED, False), (C_ARCHIVED, C_ANALYZING, False),
])
def test_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


def test_conflict_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    e.register_conflict(reg, "s", "d", T[0], commit=False)
    assert ledger.read_case_events() == []


def test_claim_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    e.add_claim(c, "a", "x", "", T[2], commit=False)
    assert ledger.read_claims() == []


def test_position_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    e.record_agent_position(c, "b", cl, "", T[3], commit=False)
    assert ledger.read_positions() == []


def test_report_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = _conflict(e)
    e.generate_report(c, "CONFLICT", T[1], commit=False)
    assert ledger.read_reports() == []


def test_conflict_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownConflictError):
        _eng().conflict_meta("CFC:ghost")


def test_claim_unknown_conflict(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownConflictError):
        _eng().add_claim("CFC:ghost", "a", "x", "", T[0], commit=True)


def test_multiple_conflicts_isolated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    c1 = e.register_conflict(reg, "s1", "", T[0], commit=True).conflict_id
    c2 = e.register_conflict(reg, "s2", "", T[0], commit=True).conflict_id
    e.start_analysis(c1, T[1], commit=True)
    e.add_claim(c1, "a", "x", "", T[2], commit=True)
    assert len(ledger.conflict_claims(c1)) == 1
    assert len(ledger.conflict_claims(c2)) == 0


def test_positions_of(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    assert set(e.positions_of(c)) == {"alpha_agent", "sim_agent", "risk_agent"}


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_conflict_resolution.verify import reference_integrity
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.attach_evidence(a, "l", "r", EV_METRIC, "", T[7], commit=True)
    assert reference_integrity()["ok"] is True


def test_session_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    assert any(x["artifact_type"] == "SESSION" for x in ledger.read_artifacts())


def test_outcome_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    assert any(x["artifact_type"] == "OUTCOME" for x in ledger.read_artifacts())


def test_unresolved_when_tie_no_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    a = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    b = e.add_claim(c, "b", "y", "", T[3], commit=True).claim_id
    e.record_agent_position(c, "a", a, "", T[4], commit=True)
    e.record_agent_position(c, "b", b, "", T[5], commit=True)
    assert e.compare_claims(c)["suggested_type"] == R_UNRESOLVED


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_conflict_resolution.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_registry_conflict_claim(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["registry", "--name", "b", "--commit"], capsys)
    reg = json.loads(out)["registry"]["registry_id"]
    rc2, out2 = _run(["conflict", "--registry", reg, "--subject", "s", "--commit"], capsys)
    cid = json.loads(out2)["conflict"]["conflict_id"]
    _run(["analyze", "--conflict", cid, "--commit"], capsys)
    rc3, out3 = _run(["claim", "--conflict", cid, "--agent", "a", "--conclusion", "x",
                      "--commit"], capsys)
    assert rc3 == 0
    assert json.loads(out3)["claim"]["agent"] == "a"


def test_cli_position_compare_resolve(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    rc, out = _run(["compare", "--conflict", c], capsys)
    assert rc == 0
    assert json.loads(out)["suggested_type"] == "MAJORITY"
    _run(["resolve-start", "--conflict", c, "--commit"], capsys)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    rc2, out2 = _run(["resolve", "--conflict", c, "--session", sess, "--type", "MAJORITY",
                      "--winning", a, "--commit"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["outcome"]["resolution_type"] == "MAJORITY"


def test_cli_evidence(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    rc, out = _run(["evidence", "--claim", cl, "--layer", "l", "--ref", "r", "--type", "METRIC",
                    "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["evidence"]["read_only"] is True


def test_cli_minority_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    rc, out = _run(["minority", "--conflict", c, "--winning", a, "--commit"], capsys)
    assert rc == 0
    assert len(json.loads(out)["minority"]) == 1
    rc2, out2 = _run(["report", "--conflict", c, "--commit"], capsys)
    assert json.loads(out2)["report"]["is_binding"] is False


def test_cli_conflicts(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _conflict(e)
    rc, out = _run(["conflicts"], capsys)
    assert rc == 0
    assert len(json.loads(out)["conflicts"]) == 1


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _with_claims(_eng())
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "claim_count" in json.loads(out)


@pytest.mark.parametrize("support,evidence,expect", [
    ({"a": 3}, {}, R_CONSENSUS),
    ({"a": 2, "b": 1}, {}, R_MAJORITY),
    ({"a": 1, "b": 1}, {"a": 2, "b": 0}, R_EVIDENCE_SUPERIOR),
    ({"a": 1, "b": 1}, {"a": 1, "b": 1}, R_UNRESOLVED),
    ({"a": 0, "b": 0}, {}, R_UNRESOLVED),
    ({"a": 2, "b": 2, "c": 1}, {"a": 5, "b": 0, "c": 0}, R_EVIDENCE_SUPERIOR),
])
def test_derive_resolution_matrix(support, evidence, expect):
    assert M.derive_resolution(support, evidence)[0] == expect


@pytest.mark.parametrize("rtype", list(M.RESOLUTION_TYPES))
def test_all_resolution_types_valid(tmp_path, monkeypatch, rtype):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    o = e.record_resolution(c, sess, rtype, a, "", T[11], commit=True)
    assert o.resolution_type == rtype


def test_evidence_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    e.attach_evidence(cl, "l", "r", EV_METRIC, "", T[3], commit=False)
    assert ledger.read_evidence() == []


def test_resolve_start_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=False)
    assert ledger.read_sessions() == []


def test_minority_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.preserve_minority_view(c, "risk_agent", "op", b, T[10], commit=False)
    assert ledger.read_minority() == []


def test_evidence_on_closed_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    with pytest.raises(ConflictClosedError):
        e.attach_evidence(a, "l", "r", EV_METRIC, "", T[12], commit=True)


def test_position_on_closed_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    with pytest.raises(ConflictClosedError):
        e.record_agent_position(c, "late", a, "", T[12], commit=True)


def test_minority_of(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.preserve_all_minority(c, a, T[10], commit=True)
    assert e.minority_of(c) == ["risk_agent"]


def test_claim_preserved_after_resolution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)
    sess = ledger.conflict_sessions(c)[0]["session_id"]
    e.record_resolution(c, sess, R_MAJORITY, a, "", T[11], commit=True)
    # 원본 주장(패배 포함) 모두 보존
    assert set(e.claims_of(c)) == {a, b}


def test_evidence_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    cl = e.add_claim(c, "a", "x", "", T[2], commit=True).claim_id
    e.attach_evidence(cl, "l", "r", EV_METRIC, "detail1", T[3], commit=True)
    from jarvis.research_conflict_resolution.models import ImmutableEvidenceError
    with pytest.raises(ImmutableEvidenceError):
        e.attach_evidence(cl, "l", "r", EV_METRIC, "detail2", T[4], commit=True)


def test_lifecycle_reanalyze_loop(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c, a, b = _with_claims(e)
    e.start_resolution(c, "", "", T[10], commit=True)  # DISCUSSING
    e.start_analysis(c, T[11], commit=True)  # DISCUSSING->ANALYZING (re-analyze)
    assert e.current_state(c) == C_ANALYZING


def test_report_lineage_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg, c = _analyzing(e)
    r = e.generate_report(c, "CONFLICT", T[2], commit=True)
    assert r.lifecycle_state == C_ANALYZING


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


# ══════════════ 통합 시나리오 (end-to-end) ══════════════
def test_end_to_end_workflow(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rvw_reviews.jsonl"), "w") as f:
        f.write(json.dumps({"review_id": "rvw_mom"}) + "\n")
    e = _eng()
    reg = e.register_registry("conflict_board", "resolve research disagreements", T[0],
                              commit=True).registry_id
    c = e.register_conflict(reg, "is momentum_v3 robust?", "alpha says yes, risk says no", T[0],
                            commit=True).conflict_id
    e.start_analysis(c, T[1], commit=True)
    # 3 agents, 2 competing claims
    a = e.add_claim(c, "alpha_agent", "robust across regimes", "IR>1, stable", T[2],
                    commit=True).claim_id
    b = e.add_claim(c, "risk_agent", "overfit post-2015", "OOS Sharpe collapses", T[3],
                    commit=True).claim_id
    e.attach_evidence(a, "research_reviewer", "rvw_mom", "REVIEW", "reviewer passed", T[4],
                      commit=True, verify_ref=True)
    e.attach_evidence(b, "research_reviewer", "rvw_mom", "REVIEW", "reproducibility weak", T[5],
                      commit=True)
    e.record_agent_position(c, "alpha_agent", a, "confident", T[6], commit=True)
    e.record_agent_position(c, "sim_agent", a, "sims agree", T[7], commit=True)
    e.record_agent_position(c, "risk_agent", b, "dissent", T[8], commit=True)
    cmp = e.compare_claims(c)
    assert cmp["suggested_type"] == R_MAJORITY
    assert cmp["leading_claim"] == a
    sess = e.start_resolution(c, "council", "analysis", T[9], commit=True).session_id
    o = e.record_resolution(c, sess, R_MAJORITY, a, "2-1 majority for robust", T[10], commit=True)
    assert o.computed_type == R_MAJORITY
    ms = e.preserve_all_minority(c, a, T[11], commit=True)
    assert len(ms) == 1 and ms[0].agent == "risk_agent"
    assert e.current_state(c) == C_RESOLVED
    e.archive_conflict(c, T[12], commit=True)
    rep = e.generate_report(c, "CONFLICT", T[13], commit=True)
    assert rep.claim_count == 2
    assert rep.evidence_count == 2
    assert rep.minority_count == 1
    assert rep.resolution_type == R_MAJORITY
    assert rep.is_binding is False
    # upstream review untouched
    assert open(sp("rvw_reviews.jsonl")).read().count("rvw_mom") == 1
    from jarvis.research_conflict_resolution.verify import verify_chain
    v = verify_chain(check_minority=True)
    assert v["ok"] is True
    assert v["lifecycle"]["ok"] and v["determinism"]["ok"] and v["reference"]["ok"] and \
        v["lineage"]["ok"] and v["minority"]["ok"]
