"""P12.4 Adaptive Research Loop 테스트. **개선 기록 전용.**

피드백·실패 분석·개선 제안 생애주기(OBSERVED→ANALYZED→PROPOSED→REVIEWED→RECORDED→ARCHIVED)·인간 리뷰 필수·금지
수정 차단·효율 비교(결정적)·적응 이력·리포트(is_binding=False)·verify(체인/변조/중복/생애주기/리뷰기록/참조)·replay·
CLI·보안(금지import·자동 수정 없음·삭제 API 없음·불변·IMPROVEMENT≠EXECUTION·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.adaptive_research_loop import ledger
from jarvis.adaptive_research_loop import models as M
from jarvis.adaptive_research_loop.engine import AdaptiveResearchLoopEngine
from jarvis.adaptive_research_loop.models import (
    ADAPTATION_CATEGORIES,
    DEC_ACCEPT,
    DEC_NOTE,
    DEC_REWORK,
    DIR_IMPROVED,
    DIR_REGRESSED,
    DIR_UNCHANGED,
    L_ANALYZED,
    L_ARCHIVED,
    L_OBSERVED,
    L_PROPOSED,
    L_RECORDED,
    L_REVIEWED,
    LOOP_STATES,
    ForbiddenModificationError,
    IllegalLoopTransition,
    ImmutableCycleError,
    ImmutableProposalError,
    InvalidCategory,
    InvalidDecision,
    MissingReviewError,
    UnknownCycleError,
    UnknownProposalError,
)
from jarvis.adaptive_research_loop.verify import (
    duplicate_integrity,
    lifecycle_integrity,
    reference_integrity,
    replay,
    review_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.adaptive_research_loop.ledger.state_path", sp)
    return sp


def _eng():
    return AdaptiveResearchLoopEngine()


def _cycle(e, name="loop1", now=T[0]):
    return e.create_adaptation_cycle(name, "improve research", now, commit=True).cycle_id


def _proposal(e, cyc=None, title="reduce overfit", now=T[2]):
    if cyc is None:
        cyc = _cycle(e)
    fb = e.create_feedback(cyc, "autonomous_research_pipeline", "CYC1", "backtest overfit",
                           "VALIDATION", T[1], commit=True).feedback_id
    return e.analyze_failure(cyc, fb, title, "reused test window", "VALIDATION", now,
                             commit=True).proposal_id


def _to_reviewed(e, pid):
    e.generate_improvement(pid, "add walk-forward", "adopt walk-forward validation", T[3],
                           commit=True)
    e.review_improvement(pid, "human_reviewer", DEC_ACCEPT, T[4], commit=True)
    return pid


# ══════════════ Phase 0 / 접두사 / 소유 ══════════════
def test_prefix_all_ledgers_arl():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("arl_")


def test_six_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 6


def test_source_ledgers_named(tmp_path, monkeypatch):
    for k in ("research_improvement", "autonomous_research_pipeline",
              "autonomous_experiment_scheduler", "research_agent_coordinator"):
        assert k in ledger.SOURCE_LEDGERS


def test_six_lifecycle_states():
    assert len(LOOP_STATES) == 6


def test_six_categories():
    assert len(ADAPTATION_CATEGORIES) == 6


# ══════════════ create_adaptation_cycle ══════════════
def test_create_cycle_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    assert cyc.startswith("ALC:")


def test_create_cycle_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_adaptation_cycle("l", "m", T[0], commit=True)
    e.create_adaptation_cycle("l", "m", T[1], commit=True)
    assert len(ledger.read_cycles()) == 1


def test_create_cycle_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_adaptation_cycle("l", "m1", T[0], commit=True)
    with pytest.raises(ImmutableCycleError):
        e.create_adaptation_cycle("l", "m2", T[1], commit=True)


# ══════════════ create_feedback ══════════════
def test_create_feedback_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    f = e.create_feedback(cyc, "layer", "REF1", "obs", "WORKFLOW", T[1], commit=True)
    assert f.feedback_id.startswith("ALF:")


def test_create_feedback_requires_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownCycleError):
        e.create_feedback("ALC:ghost", "l", "r", "o", "", T[1], commit=True)


def test_create_feedback_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(InvalidCategory):
        e.create_feedback(cyc, "l", "r", "o", "BOGUS", T[1], commit=True)


def test_create_feedback_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.create_feedback(cyc, "l", "r", "o", "", T[1], commit=True)
    e.create_feedback(cyc, "l", "r", "o", "", T[2], commit=True)
    assert len(ledger.read_feedback()) == 1


# ══════════════ analyze_failure ══════════════
def test_analyze_failure_reaches_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    assert pid.startswith("ALP:")
    assert e.current_state(pid) == L_ANALYZED


def test_analyze_failure_records_observed_then_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    states = [ev["to_state"] for ev in ledger.proposal_events(pid)]
    assert states == [L_OBSERVED, L_ANALYZED]


def test_analyze_failure_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(InvalidCategory):
        e.analyze_failure(cyc, "F1", "t", "rc", "BOGUS", T[2], commit=True)


def test_analyze_failure_duplicate_diff_root(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.analyze_failure(cyc, "F1", "t", "rc1", "WORKFLOW", T[2], commit=True)
    with pytest.raises(ImmutableProposalError):
        e.analyze_failure(cyc, "F1", "t", "rc2", "WORKFLOW", T[3], commit=True)


# ══════════════ generate_improvement ══════════════
def test_generate_improvement_reaches_proposed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "desc", "adopt walk-forward", T[3], commit=True)
    assert e.current_state(pid) == L_PROPOSED


def test_generate_improvement_forbidden_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    with pytest.raises(ForbiddenModificationError):
        e.generate_improvement(pid, "desc", "MODIFY_MODEL", T[3], commit=True)


@pytest.mark.parametrize("bad", ["MODIFY_MODEL", "MODIFY_STRATEGY", "MODIFY_PERMISSION",
                                 "AUTO_DEPLOY", "MODIFY_SYSTEM", "AUTO_UPDATE"])
def test_generate_improvement_forbidden_verbs(tmp_path, monkeypatch, bad):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e, title=f"t-{bad}")
    with pytest.raises(ForbiddenModificationError):
        e.generate_improvement(pid, "d", bad, T[3], commit=True)


def test_generate_improvement_wrong_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "d", "walk-forward", T[3], commit=True)
    with pytest.raises(IllegalLoopTransition):
        e.generate_improvement(pid, "d", "another", T[4], commit=True)


def test_generate_improvement_carries_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    ev = e.generate_improvement(pid, "d", "walk-forward validation", T[3], commit=True)
    assert ev.proposed_change == "walk-forward validation"


# ══════════════ review_improvement (human review required) ══════════════
def test_review_accept_reaches_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    e.review_improvement(pid, "human1", DEC_ACCEPT, T[4], commit=True)
    assert e.current_state(pid) == L_REVIEWED


def test_review_requires_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    with pytest.raises(MissingReviewError):
        e.review_improvement(pid, "", DEC_ACCEPT, T[4], commit=True)


def test_review_invalid_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    with pytest.raises(InvalidDecision):
        e.review_improvement(pid, "h", "MAYBE", T[4], commit=True)


def test_review_rework_back_to_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    e.review_improvement(pid, "h", DEC_REWORK, T[4], commit=True)
    assert e.current_state(pid) == L_ANALYZED


def test_review_records_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _to_reviewed(e, _proposal(e))
    rev_ev = [ev for ev in ledger.proposal_events(pid) if ev["to_state"] == L_REVIEWED][0]
    assert rev_ev["reviewer"] == "human_reviewer"


# ══════════════ record_outcome (requires human review) ══════════════
def test_record_outcome_success(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _to_reviewed(e, _proposal(e))
    a = e.record_outcome(pid, "adopted", "EVID1", "", T[5], commit=True)
    assert a.adaptation_id.startswith("ALA:")
    assert e.current_state(pid) == L_RECORDED


def test_record_outcome_requires_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    # PROPOSED 상태에서 결과 기록 불가(리뷰 필요)
    with pytest.raises(MissingReviewError):
        e.record_outcome(pid, "outcome", "", "", T[5], commit=True)


def test_record_outcome_adaptation_history(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _to_reviewed(e, _proposal(e))
    e.record_outcome(pid, "adopted", "EVID1", "", T[5], commit=True)
    assert len(ledger.proposal_adaptations(pid)) == 1


def test_archive_from_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _to_reviewed(e, _proposal(e))
    e.record_outcome(pid, "adopted", "", "", T[5], commit=True)
    e.archive_proposal(pid, T[6], commit=True)
    assert e.current_state(pid) == L_ARCHIVED


def test_full_lifecycle_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    e.review_improvement(pid, "h", DEC_ACCEPT, T[4], commit=True)
    e.record_outcome(pid, "adopted", "", "", T[5], commit=True)
    e.archive_proposal(pid, T[6], commit=True)
    states = [ev["to_state"] for ev in ledger.proposal_events(pid)]
    assert states == [L_OBSERVED, L_ANALYZED, L_PROPOSED, L_REVIEWED, L_RECORDED, L_ARCHIVED]


# ══════════════ compare_cycles (efficiency) ══════════════
def test_compare_improved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c1 = e.create_adaptation_cycle("l1", "", T[0], commit=True).cycle_id
    c2 = e.create_adaptation_cycle("l2", "", T[1], commit=True).cycle_id
    m = e.compare_cycles(c1, c2, "sharpe", 1.0, 1.5, True, T[2], commit=True)
    assert m.direction == DIR_IMPROVED
    assert m.delta == 0.5


def test_compare_regressed_lower_better(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c1 = e.create_adaptation_cycle("l1", "", T[0], commit=True).cycle_id
    c2 = e.create_adaptation_cycle("l2", "", T[1], commit=True).cycle_id
    m = e.compare_cycles(c1, c2, "cycle_time", 10.0, 20.0, False, T[2], commit=True)
    assert m.direction == DIR_REGRESSED


def test_compare_unchanged(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c1 = e.create_adaptation_cycle("l1", "", T[0], commit=True).cycle_id
    c2 = e.create_adaptation_cycle("l2", "", T[1], commit=True).cycle_id
    m = e.compare_cycles(c1, c2, "m", 5.0, 5.0, True, T[2], commit=True)
    assert m.direction == DIR_UNCHANGED


def test_compare_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c1 = e.create_adaptation_cycle("l1", "", T[0], commit=True).cycle_id
    c2 = e.create_adaptation_cycle("l2", "", T[1], commit=True).cycle_id
    a = e.compare_cycles(c1, c2, "m", 1.0, 2.0, True, T[2], commit=False)
    b = e.compare_cycles(c1, c2, "m", 1.0, 2.0, True, T[2], commit=False)
    assert a.metric_id == b.metric_id and a.delta == b.delta


def test_compare_requires_cycles(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c1 = _cycle(e)
    with pytest.raises(UnknownCycleError):
        e.compare_cycles(c1, "ALC:ghost", "m", 1.0, 2.0, True, T[2], commit=True)


@pytest.mark.parametrize("a,b,hib,exp", [
    (1.0, 2.0, True, DIR_IMPROVED),
    (2.0, 1.0, True, DIR_REGRESSED),
    (1.0, 1.0, True, DIR_UNCHANGED),
    (2.0, 1.0, False, DIR_IMPROVED),
    (1.0, 2.0, False, DIR_REGRESSED),
])
def test_compare_direction_pure(a, b, hib, exp):
    direction, _ = M.compare_direction(a, b, hib)
    assert direction == exp


# ══════════════ report ══════════════
def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    fb = e.create_feedback(cyc, "l", "R1", "obs", "WORKFLOW", T[1], commit=True).feedback_id
    pid = e.analyze_failure(cyc, fb, "t", "rc", "WORKFLOW", T[2], commit=True).proposal_id
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    e.review_improvement(pid, "h", DEC_ACCEPT, T[4], commit=True)
    e.record_outcome(pid, "adopted", "", "", T[5], commit=True)
    rep = e.generate_report(cyc, "CYCLE", T[6], commit=True)
    assert rep.feedback_count == 1
    assert rep.proposal_count == 1
    assert rep.reviewed_count == 1
    assert rep.recorded_count == 1


def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    rep = e.generate_report(cyc, "CYCLE", T[1], commit=True)
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    rep = e.generate_report(cyc, "CYCLE", T[1], commit=True)
    assert "IMPROVEMENT ≠ EXECUTION" in rep.disclaimer


def test_report_category_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.analyze_failure(cyc, "F1", "t1", "rc", "WORKFLOW", T[2], commit=True)
    e.analyze_failure(cyc, "F2", "t2", "rc", "EFFICIENCY", T[3], commit=True)
    rep = e.generate_report(cyc, "CYCLE", T[4], commit=True)
    assert rep.category_distribution.get("WORKFLOW") == 1
    assert rep.category_distribution.get("EFFICIENCY") == 1


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _to_reviewed(e, _proposal(e))
    e.record_outcome(pid, "adopted", "", "", T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposal(e)
    p = ledger.state_path(ledger.PROPOSALS[0])
    recs = ledger.read_proposal_events()
    recs[0]["root_cause"] = "TAMPERED"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposal(e)
    p = ledger.state_path(ledger.PROPOSALS[0])
    recs = ledger.read_proposal_events()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.PROPOSALS[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposal(e)
    p = ledger.state_path(ledger.PROPOSALS[0])
    recs = ledger.read_proposal_events()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.PROPOSALS[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _to_reviewed(e, _proposal(e))
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    p = ledger.state_path(ledger.PROPOSALS[0])
    g = [r for r in ledger.proposal_events(pid) if r["from_state"] == M.GENESIS][0]
    with open(p, "a") as f:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
    assert duplicate_integrity()["ok"] is False


def test_review_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _to_reviewed(e, _proposal(e))
    e.record_outcome(pid, "adopted", "", "", T[5], commit=True)
    assert review_integrity()["ok"] is True


def test_review_integrity_detects_no_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _to_reviewed(e, _proposal(e))
    e.record_outcome(pid, "adopted", "", "", T[5], commit=True)
    # REVIEWED 이벤트의 reviewer 를 지워 위조
    p = ledger.state_path(ledger.PROPOSALS[0])
    recs = ledger.read_proposal_events()
    for r in recs:
        if r["to_state"] == L_REVIEWED:
            r["reviewer"] = ""
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert review_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposal(e)
    assert reference_integrity()["ok"] is True


def test_reference_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.create_feedback(cyc, "l", "R1", "o", "", T[1], commit=True)
    p = ledger.state_path(ledger.FEEDBACK[0])
    recs = ledger.read_feedback()
    recs[0]["cycle_id"] = "ALC:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert reference_integrity()["ok"] is False


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposal(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposal(e)
    s = e.summary(T[9])
    assert s.cycle_count == 1
    assert s.feedback_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposal(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposal(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_proposals_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    assert pid in e.proposals_in_state(L_ANALYZED)


def test_list_proposals_by_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _proposal(e, cyc=cyc)
    assert len(e.list_proposals(cyc)) == 1


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (L_OBSERVED, L_ANALYZED, True),
    (L_ANALYZED, L_PROPOSED, True),
    (L_PROPOSED, L_REVIEWED, True),
    (L_REVIEWED, L_RECORDED, True),
    (L_REVIEWED, L_ANALYZED, True),
    (L_RECORDED, L_ARCHIVED, True),
    (L_OBSERVED, L_PROPOSED, False),
    (L_OBSERVED, L_RECORDED, False),
    (L_ARCHIVED, L_RECORDED, False),
    (L_PROPOSED, L_RECORDED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["AUTO_UPDATE", "AUTO_DEPLOY", "AUTO_PROMOTE", "MODIFY_SYSTEM",
                                  "MODIFY_MODEL", "MODIFY_STRATEGY", "MODIFY_PERMISSION", "DEPLOY"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["OBSERVE", "ANALYZE", "PROPOSE", "REVIEW", "RECORD", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.cycle_id("x") == M.cycle_id("x")
    assert M.proposal_id("c", "t") == M.proposal_id("c", "t")


def test_ids_prefixes_al_scheme():
    assert M.cycle_id("x").startswith("ALC:")
    assert M.feedback_id("c", "r", "o").startswith("ALF:")
    assert M.proposal_id("c", "t").startswith("ALP:")
    assert M.proposal_event_id("p", "s", 0).startswith("ALV:")
    assert M.metric_id("a", "b", "m").startswith("ALM:")
    assert M.adaptation_id("p", 0).startswith("ALA:")
    assert M.report_id("c", "s", "t").startswith("ALR:")


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
    forbidden = ("def auto_update", "def auto_deploy", "def auto_promote", "def modify_system",
                 "def modify_model", "def modify_strategy", "def modify_permission", "def deploy")
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
    import jarvis.adaptive_research_loop.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_arl_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _to_reviewed(e, _proposal(e))
    e.record_outcome(pid, "adopted", "", "", T[5], commit=True)
    c2 = e.create_adaptation_cycle("l2", "", T[6], commit=True).cycle_id
    m = e.proposal_meta(pid)
    e.compare_cycles(m["cycle_id"], c2, "sharpe", 1.0, 1.2, True, T[7], commit=True)
    e.generate_report(m["cycle_id"], "CYCLE", T[8], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("arl_"), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("research_improvement", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("rimp_registry.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"registry_id": "R1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("research_improvement", "R1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.adaptive_research_loop.__main__ import main
    assert main(["summary"]) == 0
    assert "cycle_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.adaptive_research_loop.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.adaptive_research_loop.__main__ import main
    main(["cycle", "--name", "l1", "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    main(["feedback", "--cycle", cyc, "--layer", "L", "--ref", "R1", "--observation", "obs",
          "--commit"])
    fb = json.loads(capsys.readouterr().out)["feedback"]["feedback_id"]
    main(["analyze", "--cycle", cyc, "--feedback", fb, "--title", "t", "--root", "rc", "--commit"])
    pid = json.loads(capsys.readouterr().out)["proposal"]["proposal_id"]
    main(["improve", "--proposal", pid, "--description", "d", "--change", "walk-forward",
          "--commit"])
    capsys.readouterr()
    main(["review", "--proposal", pid, "--reviewer", "h", "--decision", "ACCEPT", "--commit"])
    capsys.readouterr()
    assert main(["outcome", "--proposal", pid, "--outcome", "adopted", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["adaptation"]["outcome"] == "adopted"


def test_cli_compare(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.adaptive_research_loop.__main__ import main
    main(["cycle", "--name", "l1", "--commit"])
    c1 = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    main(["cycle", "--name", "l2", "--commit"])
    c2 = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    assert main(["compare", "--cycle-a", c1, "--cycle-b", c2, "--metric", "m", "--value-a", "1",
                 "--value-b", "2", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["metric"]["direction"] == DIR_IMPROVED


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.adaptive_research_loop.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.adaptive_research_loop.__main__ import main
    main(["cycle", "--name", "l1", "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    assert main(["report", "--cycle", cyc, "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["is_binding"] is False


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("cat", list(ADAPTATION_CATEGORIES))
def test_analyze_all_categories(tmp_path, monkeypatch, cat):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    ev = e.analyze_failure(cyc, "F1", "t-" + cat, "rc", cat, T[2], commit=True)
    assert ev.category == cat


@pytest.mark.parametrize("st", list(LOOP_STATES))
def test_state_membership(st):
    assert st in LOOP_STATES


@pytest.mark.parametrize("name", ["a", "b", "c", "d"])
def test_multiple_cycles(tmp_path, monkeypatch, name):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = e.create_adaptation_cycle(name, "", T[0], commit=True)
    assert c.name == name


def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_adaptation_cycle("l", "m", T[0], commit=False)
    assert ledger.read_cycles() == []


def test_proposal_meta_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e, title="tighten")
    m = e.proposal_meta(pid)
    assert m["title"] == "tighten" and m["category"] == "VALIDATION"


def test_proposal_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownProposalError):
        e.proposal_meta("ALP:ghost")


def test_note_decision_stays_reviewed_path(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    e.review_improvement(pid, "h", DEC_NOTE, T[4], commit=True)
    assert e.current_state(pid) == L_REVIEWED


def test_metric_immutable_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c1 = e.create_adaptation_cycle("l1", "", T[0], commit=True).cycle_id
    c2 = e.create_adaptation_cycle("l2", "", T[1], commit=True).cycle_id
    e.compare_cycles(c1, c2, "m", 1.0, 2.0, True, T[2], commit=True)
    e.compare_cycles(c1, c2, "m", 1.0, 2.0, True, T[3], commit=True)
    assert len(ledger.read_metrics()) == 1


@pytest.mark.parametrize("title", ["t1", "t2", "t3", "t4", "t5"])
def test_multiple_proposals(tmp_path, monkeypatch, title):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    pid = e.analyze_failure(cyc, "F1", title, "rc", "WORKFLOW", T[2], commit=True).proposal_id
    assert e.proposal_meta(pid)["title"] == title


@pytest.mark.parametrize("dec", [DEC_ACCEPT, DEC_NOTE])
def test_review_decisions_reach_reviewed(tmp_path, monkeypatch, dec):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e, title=f"t-{dec}")
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    e.review_improvement(pid, "h", dec, T[4], commit=True)
    assert e.current_state(pid) == L_REVIEWED


def test_rework_then_repropose(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    e.generate_improvement(pid, "d", "wf", T[3], commit=True)
    e.review_improvement(pid, "h", DEC_REWORK, T[4], commit=True)
    assert e.current_state(pid) == L_ANALYZED
    e.generate_improvement(pid, "d2", "wf2", T[5], commit=True)
    assert e.current_state(pid) == L_PROPOSED


def test_review_wrong_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _proposal(e)
    # ANALYZED 상태에서 리뷰 불가(PROPOSED 필요)
    with pytest.raises(IllegalLoopTransition):
        e.review_improvement(pid, "h", DEC_ACCEPT, T[4], commit=True)


def test_generate_improvement_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownProposalError):
        e.generate_improvement("ALP:ghost", "d", "wf", T[3], commit=True)


def test_record_outcome_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownProposalError):
        e.record_outcome("ALP:ghost", "o", "", "", T[5], commit=True)


def test_feedback_category_optional(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    f = e.create_feedback(cyc, "l", "R1", "obs", "", T[1], commit=True)
    assert f.category == ""


def test_adaptation_carries_evidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    pid = _to_reviewed(e, _proposal(e))
    a = e.record_outcome(pid, "adopted", "EVIDENCE_X", "note", T[5], commit=True)
    assert a.evidence_ref == "EVIDENCE_X"


def test_cycle_feedback_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c1 = e.create_adaptation_cycle("l1", "", T[0], commit=True).cycle_id
    c2 = e.create_adaptation_cycle("l2", "", T[0], commit=True).cycle_id
    e.create_feedback(c1, "l", "R1", "o", "", T[1], commit=True)
    e.create_feedback(c2, "l", "R2", "o", "", T[2], commit=True)
    assert len(ledger.cycle_feedback(c1)) == 1


def test_compare_delta_rounding():
    _, delta = M.compare_direction(1.0, 1.123456789, True)
    assert delta == 0.12345679


def test_metric_value_rounding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c1 = e.create_adaptation_cycle("l1", "", T[0], commit=True).cycle_id
    c2 = e.create_adaptation_cycle("l2", "", T[1], commit=True).cycle_id
    m = e.compare_cycles(c1, c2, "x", 1.111111119, 2.0, True, T[2], commit=True)
    assert m.value_a == round(1.111111119, 8)


def test_report_metric_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c1 = e.create_adaptation_cycle("l1", "", T[0], commit=True).cycle_id
    c2 = e.create_adaptation_cycle("l2", "", T[1], commit=True).cycle_id
    e.compare_cycles(c1, c2, "m", 1.0, 2.0, True, T[2], commit=True)
    rep = e.generate_report(c1, "CYCLE", T[3], commit=True)
    assert rep.metric_count == 1


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_proposal_event_id_varies_seq():
    assert M.proposal_event_id("p", "ANALYZED", 0) != M.proposal_event_id("p", "ANALYZED", 1)


def test_verify_all_ledgers_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposal(e)
    res = verify_chain()
    for fn, _ in ledger.ALL_LEDGERS:
        assert fn in res["ledgers"]


def test_end_to_end_adaptive_loop(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = e.create_adaptation_cycle("momentum_loop", "improve momentum research", T[0],
                                    commit=True).cycle_id
    fb = e.create_feedback(cyc, "autonomous_research_pipeline", "CYC1",
                           "backtest overfit on in-sample", "VALIDATION", T[1], commit=True).feedback_id
    pid = e.analyze_failure(cyc, fb, "prevent in-sample overfit", "reused test window",
                            "VALIDATION", T[2], commit=True).proposal_id
    e.generate_improvement(pid, "adopt walk-forward", "walk-forward validation windows", T[3],
                           commit=True)
    e.review_improvement(pid, "senior_researcher", DEC_ACCEPT, T[4], commit=True)
    e.record_outcome(pid, "process updated in playbook", "PLAYBOOK_V2", "", T[5], commit=True)
    assert e.current_state(pid) == L_RECORDED
    c2 = e.create_adaptation_cycle("momentum_loop_v2", "", T[6], commit=True).cycle_id
    m = e.compare_cycles(cyc, c2, "oos_sharpe", 0.8, 1.2, True, T[7], commit=True)
    assert m.direction == DIR_IMPROVED
    rep = e.generate_report(cyc, "CYCLE", T[8], commit=True)
    assert rep.recorded_count == 1
    assert verify_chain()["ok"] is True
