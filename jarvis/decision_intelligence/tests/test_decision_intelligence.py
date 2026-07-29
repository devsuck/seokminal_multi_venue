"""P10.7 Research Decision Intelligence 테스트. **판단 지원 전용.**

후보 레지스트리(불변)·생명주기(REGISTERED→...→ARCHIVED, 차단전이)·결정 세션(CREATED→...→ARCHIVED)·
평가 프레임워크(버전·불변)·스코어카드(MCDA)·트레이드오프(자동추천 없음)·결정 리포트·계보·verify(체인/
변조/중복/계보/dangling/cycle)·replay·ingest(상위 READ ONLY)·CLI·보안(금지import·선택/배포/실행/
자본배분/권한변경 없음·상위 원장 무변경·삭제 API 없음·불변·score≠approval·RECOMMENDED≠DEPLOYABLE·
append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.decision_intelligence import ledger
from jarvis.decision_intelligence import models as M
from jarvis.decision_intelligence.engine import ResearchDecisionEngine
from jarvis.decision_intelligence.models import (
    ARCHIVED,
    COMPARED,
    COMPLETED,
    CREATED,
    EVALUATING,
    REGISTERED,
    REPORTED,
    SCORED,
    UNDER_REVIEW,
    IllegalTransition,
    ImmutableCandidateError,
    ImmutableFrameworkError,
    UnknownCandidate,
    UnknownFramework,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_SCORES_A = {"performance": 0.9, "robustness": 0.8, "risk": 0.7, "complexity": 0.4,
             "data_quality": 0.85, "reproducibility": 0.8, "confidence": 0.7}
_SCORES_B = {"performance": 0.6, "robustness": 0.9, "risk": 0.9, "complexity": 0.8,
             "data_quality": 0.7, "reproducibility": 0.75, "confidence": 0.6}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.decision_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchDecisionEngine()


def _cand(eng, layer="research_governance", ref="ST1", rtype="STRATEGY", commit=True):
    return eng.register_candidate(layer, ref, rtype, {"k": ref}, T0, commit=commit)


def _fw(eng, name="mcda", ver="1", commit=True):
    return eng.define_framework(name, ver, None, None, T0, commit=commit)


def _session(eng, cands, obj="pick best", ev="human_pm", commit=True):
    return eng.create_decision_session(obj, ev, cands, T0, commit=commit)


def _full(eng):
    """두 후보 등록→프레임워크→세션→평가→비교→리포트 전체 시나리오."""
    a = _cand(eng, "research_governance", "ST1", "STRATEGY")
    b = _cand(eng, "portfolio_research", "PF1", "PORTFOLIO")
    fw = _fw(eng)
    s = _session(eng, [a.candidate_id, b.candidate_id])
    eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id, _SCORES_A, now=T1,
                           commit=True)
    eng.evaluate_candidate(s.session_id, b.candidate_id, fw.framework_id, _SCORES_B, now=T1,
                           commit=True)
    eng.compare_candidates(s.session_id, a.candidate_id, b.candidate_id, T1, commit=True)
    rep = eng.create_decision_snapshot(s.session_id, T2, commit=True)
    return a, b, fw, s, rep


# ── Candidate Registry ──
def test_register_candidate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cand(eng)
    assert c.status == REGISTERED and c.research_type == "STRATEGY"
    assert eng.candidate_state(c.candidate_id) == REGISTERED


def test_candidate_id_deterministic():
    a = M.candidate_id("l", "r")
    assert a == M.candidate_id("l", "r") and a.startswith("DIC:")


def test_candidate_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _cand(_eng(), commit=True)
    assert len(ledger.read_candidate_events()) == 1


def test_candidate_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _cand(_eng(), commit=False)
    assert ledger.read_candidate_events() == []


def test_candidate_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_candidate("l", "r", "STRATEGY", {"a": 1}, T0, commit=True)
    with pytest.raises(ImmutableCandidateError):
        eng.register_candidate("l", "r", "STRATEGY", {"a": 2}, T0, commit=True)


def test_candidate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _cand(eng)
    _cand(eng)
    assert len(ledger.distinct_candidates()) == 1


def test_candidate_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cand(eng)
    cid = c.candidate_id
    eng.transition_candidate(cid, UNDER_REVIEW, T1, commit=True)
    eng.transition_candidate(cid, SCORED, T1, commit=True)
    eng.transition_candidate(cid, COMPARED, T1, commit=True)
    eng.transition_candidate(cid, REPORTED, T2, commit=True)
    eng.transition_candidate(cid, ARCHIVED, T2, commit=True)
    assert eng.candidate_state(cid) == ARCHIVED


def test_candidate_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cand(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_candidate(c.candidate_id, SCORED, T1, commit=True)  # REGISTERED→SCORED 차단


def test_candidate_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cand(eng)
    for to in (UNDER_REVIEW, SCORED, REPORTED, ARCHIVED):
        eng.transition_candidate(c.candidate_id, to, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_candidate(c.candidate_id, REGISTERED, T2, commit=True)


def test_candidate_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownCandidate):
        _eng().transition_candidate("GHOST", UNDER_REVIEW, T1, commit=True)


def test_candidate_transition_table():
    assert M.can_transition_candidate("", REGISTERED)
    assert M.can_transition_candidate(SCORED, COMPARED)
    assert M.can_transition_candidate(SCORED, REPORTED)
    assert not M.can_transition_candidate(REGISTERED, COMPARED)
    assert not M.can_transition_candidate(ARCHIVED, REPORTED)


def test_candidate_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cand(eng)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    cart = arts[M.artifact_id(M.ART_CANDIDATE, c.candidate_id)]
    assert cart["parent_artifact"] == M.artifact_id(M.ART_SOURCE, "research_governance:ST1")
    assert cart["parent_artifact"] in arts


# ── Decision Session ──
def test_create_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    s = _session(eng, [a.candidate_id])
    assert s.status == CREATED and a.candidate_id in s.candidates


def test_session_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    s = _session(eng, [a.candidate_id])
    eng.transition_session(s.session_id, EVALUATING, T1, commit=True)
    eng.transition_session(s.session_id, COMPLETED, T2, commit=True)
    eng.transition_session(s.session_id, ARCHIVED, T2, commit=True)
    assert eng.session_state(s.session_id) == ARCHIVED


def test_session_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    s = _session(eng, [a.candidate_id])
    with pytest.raises(IllegalTransition):
        eng.transition_session(s.session_id, COMPLETED, T1, commit=True)  # CREATED→COMPLETED 차단


def test_session_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    _session(eng, [a.candidate_id])
    _session(eng, [a.candidate_id])
    assert len(ledger.distinct_sessions()) == 1


def test_session_transition_table():
    assert M.can_transition_session("", CREATED)
    assert M.can_transition_session(CREATED, EVALUATING)
    assert M.can_transition_session(EVALUATING, COMPLETED)
    assert not M.can_transition_session(CREATED, COMPLETED)


def test_session_missing_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(IllegalTransition):
        _eng().transition_session("GHOST", EVALUATING, T1, commit=True)


# ── Evaluation Framework ──
def test_define_framework_default_weights(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    fw = _fw(eng)
    assert fw.weights == M.DEFAULT_WEIGHTS
    assert set(fw.criteria) == set(M.SCORE_DIMENSIONS)


def test_framework_versioning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    f1 = eng.define_framework("mcda", "1", None, {"performance": 1.0}, T0, commit=True)
    f2 = eng.define_framework("mcda", "2", None, {"risk": 1.0}, T0, commit=True)
    assert f1.framework_id != f2.framework_id
    assert len(ledger.read_frameworks()) == 2


def test_framework_immutable_same_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.define_framework("mcda", "1", None, {"performance": 1.0}, T0, commit=True)
    with pytest.raises(ImmutableFrameworkError):
        eng.define_framework("mcda", "1", None, {"risk": 1.0}, T0, commit=True)


def test_framework_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _fw(eng)
    _fw(eng)
    assert len(ledger.read_frameworks()) == 1


def test_framework_custom_weights_normalized_in_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    fw = eng.define_framework("w", "1", ["performance", "risk"],
                              {"performance": 3, "risk": 1}, T0, commit=True)
    a = _cand(eng)
    s = _session(eng, [a.candidate_id])
    sc = eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id,
                                {"performance": 1.0, "risk": 0.0}, now=T1, commit=True)
    assert abs(sc.overall_score - 0.75) < 1e-6  # 3/(3+1)


# ── Scorecard / MCDA ──
def test_overall_score_calculation():
    scores = {d: 1.0 for d in M.DEFAULT_WEIGHTS}
    assert abs(M.overall_score(scores, M.DEFAULT_WEIGHTS) - 1.0) < 1e-9


def test_overall_score_weighted():
    scores = {"performance": 1.0, "risk": 0.0}
    weights = {"performance": 0.5, "risk": 0.5}
    assert abs(M.overall_score(scores, weights) - 0.5) < 1e-9


def test_evaluate_candidate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    fw = _fw(eng)
    s = _session(eng, [a.candidate_id])
    sc = eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id, _SCORES_A,
                                now=T1, commit=True)
    assert 0.0 <= sc.overall_score <= 1.0
    assert len(ledger.read_scorecards()) == 1


def test_evaluate_advances_candidate_to_scored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    fw = _fw(eng)
    s = _session(eng, [a.candidate_id])
    eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id, _SCORES_A, now=T1,
                           commit=True)
    assert eng.candidate_state(a.candidate_id) == SCORED


def test_evaluate_advances_session_to_evaluating(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    fw = _fw(eng)
    s = _session(eng, [a.candidate_id])
    eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id, _SCORES_A, now=T1,
                           commit=True)
    assert eng.session_state(s.session_id) == EVALUATING


def test_evaluate_unknown_framework(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    s = _session(eng, [a.candidate_id])
    with pytest.raises(UnknownFramework):
        eng.evaluate_candidate(s.session_id, a.candidate_id, "GHOST", _SCORES_A, now=T1,
                               commit=True)


def test_evaluate_unknown_candidate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    fw = _fw(eng)
    s = eng.create_decision_session("o", "e", ["DIC:ghost"], T0, commit=True)
    with pytest.raises(UnknownCandidate):
        eng.evaluate_candidate(s.session_id, "DIC:ghost", fw.framework_id, _SCORES_A, now=T1,
                               commit=True)


def test_evaluate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    fw = _fw(eng)
    s = _session(eng, [a.candidate_id])
    eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id, _SCORES_A, now=T1,
                           commit=True)
    eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id, _SCORES_A, now=T1,
                           commit=True)
    assert len(ledger.read_scorecards()) == 1


def test_scorecard_only_framework_criteria(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    fw = eng.define_framework("w", "1", ["performance"], {"performance": 1.0}, T0, commit=True)
    a = _cand(eng)
    s = _session(eng, [a.candidate_id])
    sc = eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id,
                                {"performance": 0.5, "risk": 0.9}, now=T1, commit=True)
    assert set(sc.scores) == {"performance"}  # risk 무시(프레임워크 기준 아님)


# ── Trade-off Analysis ──
def test_tradeoff_symbols():
    assert M.tradeoff_symbol(0.9) == "+++"
    assert M.tradeoff_symbol(0.6) == "++"
    assert M.tradeoff_symbol(0.3) == "+"
    assert M.tradeoff_symbol(0.1) == "-"


def test_compare_candidates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, _ = _full(eng)
    t = ledger.read_tradeoffs()[0]
    assert t["candidate_a"] in (a.candidate_id, b.candidate_id)
    assert "performance" in t["dimensions"]
    assert t["dimensions"]["performance"]["a"] in ("+++", "++", "+", "-")


def test_compare_no_auto_recommendation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, _ = _full(eng)
    t = ledger.read_tradeoffs()[0]
    assert "자동 추천" in t["note"] and "선택" in t["note"]
    assert "recommendation" not in t  # 추천 필드 자체가 없다


def test_compare_advances_to_compared(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, _ = _full(eng)
    assert eng.candidate_state(a.candidate_id) in (COMPARED, REPORTED)


def test_compare_idempotent_symmetric(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng, "l", "A", "STRATEGY")
    b = _cand(eng, "l", "B", "STRATEGY")
    fw = _fw(eng)
    s = _session(eng, [a.candidate_id, b.candidate_id])
    eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id, _SCORES_A, now=T1,
                           commit=True)
    eng.evaluate_candidate(s.session_id, b.candidate_id, fw.framework_id, _SCORES_B, now=T1,
                           commit=True)
    eng.compare_candidates(s.session_id, a.candidate_id, b.candidate_id, T1, commit=True)
    eng.compare_candidates(s.session_id, b.candidate_id, a.candidate_id, T1, commit=True)
    assert len(ledger.read_tradeoffs()) == 1


def test_tradeoff_delta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, _ = _full(eng)
    t = ledger.read_tradeoffs()[0]
    # delta = score_a - score_b for whichever is a
    for d, v in t["dimensions"].items():
        assert "delta" in v


# ── Decision Report ──
def test_decision_report_ranking(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, rep = _full(eng)
    assert rep.candidate_count == 2 and rep.scorecard_count == 2
    assert len(rep.ranking) == 2
    # ranking sorted desc by overall_score
    assert rep.ranking[0]["overall_score"] >= rep.ranking[1]["overall_score"]


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, rep = _full(eng)
    assert "approval" in rep.disclaimer and "DEPLOYABLE" in rep.disclaimer


def test_report_ranking_not_selection(tmp_path, monkeypatch):
    """ranking 은 참고 순위일 뿐 — 선택/배포 필드 없음."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, rep = _full(eng)
    d = rep.to_dict()
    assert "selected" not in d and "deployed" not in d and "approved" not in d


def test_report_advances_session_completed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, rep = _full(eng)
    assert eng.session_state(s.session_id) == COMPLETED


def test_report_advances_candidates_reported(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, rep = _full(eng)
    assert eng.candidate_state(a.candidate_id) == REPORTED


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, _ = _full(eng)
    eng.create_decision_snapshot(s.session_id, T2, commit=True)
    assert len(ledger.read_reports()) == 1


def test_generate_tradeoff_report_alias(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, _ = _full(eng)
    r = eng.generate_tradeoff_report(s.session_id, T2, commit=True)
    assert r.session_id == s.session_id


def test_report_empty_session_no_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import verify_chain
    eng = _eng()
    a = _cand(eng)
    s = _session(eng, [a.candidate_id])
    eng.create_decision_snapshot(s.session_id, T2, commit=True)  # no scorecards
    assert verify_chain()["ok"] is True  # 루트 부모 → dangling 없음


# ── ingest (상위 READ ONLY) ──
def _seed(sp, filename, rows):
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_ingest_candidates(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_strategies.jsonl", [{"strategy_id": "ST1"}, {"strategy_id": "ST2"}])
    eng = _eng()
    n = eng.ingest_candidates("STRATEGY", T0, commit=True)
    assert n == 2 and len(ledger.distinct_candidates()) == 2


def test_ingest_does_not_mutate_source(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "ai_signals.jsonl", [{"signal_id": "SG1"}])
    before = hashlib.sha256(open(sp("ai_signals.jsonl"), "rb").read()).hexdigest()
    _eng().ingest_candidates("SIGNAL", T0, commit=True)
    after = hashlib.sha256(open(sp("ai_signals.jsonl"), "rb").read()).hexdigest()
    assert before == after


def test_ingest_limit(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "pr_portfolios.jsonl", [{"portfolio_id": f"P{i}"} for i in range(5)])
    n = _eng().ingest_candidates("PORTFOLIO", T0, commit=True, limit=2)
    assert n == 2


def test_ingest_unknown_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().ingest_candidates("NOPE", T0, commit=True) == 0


def test_ingest_all_source_types(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_strategies.jsonl", [{"strategy_id": "S"}])
    _seed(sp, "ai_signals.jsonl", [{"signal_id": "G"}])
    _seed(sp, "pr_portfolios.jsonl", [{"portfolio_id": "P"}])
    _seed(sp, "kg_entities.jsonl", [{"entity_id": "E"}])
    _seed(sp, "arg_proposals.jsonl", [{"proposal_id": "PR"}])
    eng = _eng()
    for rt in ("STRATEGY", "SIGNAL", "PORTFOLIO", "GRAPH", "AGENT_RESEARCH"):
        eng.ingest_candidates(rt, T0, commit=True)
    assert len(ledger.distinct_candidates()) == 5


# ── Report / summary ──
def test_summary_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_report(T2)
    assert rep.candidate_count == 2 and rep.session_count == 1
    assert rep.framework_count == 1 and rep.scorecard_count == 2
    assert rep.tradeoff_count == 1 and rep.report_count == 1


def test_summary_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_report(T2)
    assert rep.research_type_distribution.get("STRATEGY") == 1
    assert rep.research_type_distribution.get("PORTFOLIO") == 1
    assert rep.candidate_state_distribution.get(REPORTED) == 2


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.generate_report(T2).to_dict() == eng.generate_report(T2).to_dict()


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().generate_report(T0)
    assert rep.candidate_count == 0 and rep.report_count == 0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_scenario_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import verify_chain
    eng = _eng()
    _full(eng)
    res = verify_chain()
    assert res["ok"] is True and res["lineage"]["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import verify_chain
    eng = _eng()
    _cand(eng)
    recs = ledger.read_candidate_events()
    recs[0]["source_reference"] = "TAMPERED"
    with open(sp("di_candidates.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import verify_ledger
    eng = _eng()
    _cand(eng, "l", "A")
    _cand(eng, "l", "B")
    recs = ledger.read_candidate_events()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("di_candidates.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.CANDIDATES)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import verify_ledger
    eng = _eng()
    _cand(eng)
    recs = ledger.read_candidate_events()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("di_candidates.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.CANDIDATES)["ok"] is False


def test_verify_detects_dangling_scorecard(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import lineage_validation
    rec = {"scorecard_id": "DSC:x", "session_id": "DSS:ghost", "candidate_id": "DIC:ghost",
           "framework_id": "DFW:ghost", "scores": {}, "evidence": {}, "explanations": {},
           "overall_score": 0.0, "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("di_scorecards.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = lineage_validation()
    assert res["ok"] is False
    assert any("dangling_scorecard" in i for i in res["issues"])


def test_verify_detects_artifact_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import lineage_validation
    a1 = {"artifact_id": "A1", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A2",
          "session_id": "", "created_at": T0, "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "A2", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A1",
          "session_id": "", "created_at": T0, "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("di_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    res = lineage_validation()
    assert any("circular_dependency" in i for i in res["issues"])


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import replay
    eng = _eng()
    _full(eng)
    assert replay(eng, T2)["deterministic"] is True


# ── content hash ──
def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


def test_metadata_hash_stable():
    assert M.metadata_hash({"a": 1, "b": 2}) == M.metadata_hash({"b": 2, "a": 1})


# ── CLI ──
def test_cli_candidate_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.__main__ import main
    rc = main(["candidate", "--source-layer", "research_governance", "--source-reference",
               "ST1", "--research-type", "STRATEGY", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["candidate"]["research_type"] == "STRATEGY"
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["candidate_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.__main__ import main
    main(["candidate", "--source-layer", "l", "--source-reference", "A", "--research-type",
          "STRATEGY", "--commit"])
    ca = json.loads(capsys.readouterr().out)["candidate"]["candidate_id"]
    main(["candidate", "--source-layer", "l", "--source-reference", "B", "--research-type",
          "STRATEGY", "--commit"])
    cb = json.loads(capsys.readouterr().out)["candidate"]["candidate_id"]
    main(["framework", "--name", "mcda", "--version", "1", "--commit"])
    fid = json.loads(capsys.readouterr().out)["framework"]["framework_id"]
    main(["session", "--objective", "pick", "--evaluator", "human", "--candidates",
          f"{ca},{cb}", "--commit"])
    sid = json.loads(capsys.readouterr().out)["session"]["session_id"]
    main(["evaluate", "--session-id", sid, "--candidate-id", ca, "--framework-id", fid,
          "--scores-json", json.dumps(_SCORES_A), "--commit"])
    main(["evaluate", "--session-id", sid, "--candidate-id", cb, "--framework-id", fid,
          "--scores-json", json.dumps(_SCORES_B), "--commit"])
    capsys.readouterr()
    main(["compare", "--session-id", sid, "--candidate-a", ca, "--candidate-b", cb, "--commit"])
    t = json.loads(capsys.readouterr().out)["tradeoff"]
    assert "note" in t
    main(["report", "--session-id", sid, "--commit"])
    rep = json.loads(capsys.readouterr().out)["report"]
    assert rep["candidate_count"] == 2
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.__main__ import main
    main(["candidate", "--source-layer", "l", "--source-reference", "A", "--research-type",
          "STRATEGY", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_verify_returns_zero_empty(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.__main__ import main
    assert main(["verify"]) == 0
    capsys.readouterr()


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.decision_intelligence.engine as eng_mod
    import jarvis.decision_intelligence.models as mdl_mod
    import jarvis.decision_intelligence.ledger as led_mod
    import jarvis.decision_intelligence.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio.", _j + "risk_governor", _j + "permission",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "promote_model(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_authority_api():
    api = set(dir(ResearchDecisionEngine))
    for banned in ("execute", "deploy", "allocate", "promote", "trade", "activate_live",
                   "approve_for_trading", "select_candidate", "select", "place_order"):
        assert banned not in api


def test_score_not_approval(tmp_path, monkeypatch):
    """스코어카드/리포트에 승인·배포·선택 필드가 없어야 한다 — 판단 지원 데이터일 뿐."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, rep = _full(eng)
    sc = ledger.read_scorecards()[0]
    for banned in ("approved", "selected", "deployed", "deployable", "approval"):
        assert banned not in sc


def test_recommended_not_deployable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, rep = _full(eng)
    assert not hasattr(eng, "deploy_candidate")
    assert not hasattr(eng, "select_winner")


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.decision_intelligence.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_di_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("di_")


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for rt, (layer, fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert fn not in owned


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 P10.2~P10.6 원장을 시드한 뒤 전체 워크플로를 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"rg_strategies.jsonl": [{"strategy_id": "ST1"}],
             "ai_signals.jsonl": [{"signal_id": "SG1"}],
             "pr_portfolios.jsonl": [{"portfolio_id": "PF1"}],
             "kg_entities.jsonl": [{"entity_id": "KGE:1"}],
             "arg_proposals.jsonl": [{"proposal_id": "APP:1"}]}
    hashes = {}
    for fn, rows in seeds.items():
        _seed(sp, fn, rows)
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    for rt in ("STRATEGY", "SIGNAL", "PORTFOLIO", "GRAPH", "AGENT_RESEARCH"):
        eng.ingest_candidates(rt, T0, commit=True)
    # 전체 워크플로를 ingest 된 후보 위에서 수행(중복 등록 없이).
    cands = [c["candidate_id"] for c in ledger.distinct_candidates()]
    fw = _fw(eng)
    s = _session(eng, cands[:2])
    eng.evaluate_candidate(s.session_id, cands[0], fw.framework_id, _SCORES_A, now=T1,
                           commit=True)
    eng.evaluate_candidate(s.session_id, cands[1], fw.framework_id, _SCORES_B, now=T1,
                           commit=True)
    eng.compare_candidates(s.session_id, cands[0], cands[1], T1, commit=True)
    eng.create_decision_snapshot(s.session_id, T2, commit=True)
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_engine_only_appends_di_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("di_") for f in created)


def test_no_collision_with_existing_prefixes():
    """di_ 원장이 기존 어떤 레이어 원장과도 파일명이 겹치지 않아야 한다."""
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"dg_datasets.jsonl", "mg_models.jsonl", "ag_operators.jsonl", "rg_strategies.jsonl",
             "ai_signals.jsonl", "pr_portfolios.jsonl", "kg_entities.jsonl", "arg_agents.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("di_") for fn in ours)


# ── 추가: MCDA/헬퍼/불변식 세부 ──
def test_normalize_weights_sums_to_one():
    w = M.normalize_weights({"a": 2, "b": 2})
    assert abs(sum(w.values()) - 1.0) < 1e-9 and w["a"] == 0.5


def test_normalize_weights_empty():
    assert M.normalize_weights({}) == {}


def test_overall_score_missing_dim_treated_zero():
    assert M.overall_score({"performance": 1.0}, {"performance": 0.5, "risk": 0.5}) == 0.5


def test_overall_score_zero_weights():
    assert M.overall_score({"performance": 1.0}, {}) == 0.0


def test_default_weights_sum_close_to_one():
    assert abs(sum(M.DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9


def test_tradeoff_symbol_boundaries():
    assert M.tradeoff_symbol(0.75) == "+++"
    assert M.tradeoff_symbol(0.5) == "++"
    assert M.tradeoff_symbol(0.25) == "+"
    assert M.tradeoff_symbol(0.0) == "-"


def test_candidate_id_varies():
    assert M.candidate_id("l", "A") != M.candidate_id("l", "B")
    assert M.candidate_id("x", "A") != M.candidate_id("y", "A")


def test_artifact_id_prefix():
    assert M.artifact_id(M.ART_CANDIDATE, "x").startswith("DIA:")


def test_scorecard_evidence_explanations_passthrough(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _cand(eng)
    fw = _fw(eng)
    s = _session(eng, [a.candidate_id])
    sc = eng.evaluate_candidate(s.session_id, a.candidate_id, fw.framework_id, _SCORES_A,
                                {"performance": "backtest#1"}, {"performance": "high sharpe"},
                                T1, commit=True)
    assert sc.evidence["performance"] == "backtest#1"
    assert sc.explanations["performance"] == "high sharpe"


def test_tradeoff_overall_values(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, _ = _full(eng)
    t = ledger.read_tradeoffs()[0]
    assert 0.0 <= t["overall_a"] <= 1.0 and 0.0 <= t["overall_b"] <= 1.0


def test_report_objective_evaluator_carried(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b, fw, s, rep = _full(eng)
    assert rep.objective == "pick best" and rep.evaluator == "human_pm"


def test_session_id_deterministic_on_candidate_order():
    assert M.session_id("o", "e", ["b", "a"]) == M.session_id("o", "e", ["a", "b"])


def test_safe_advance_candidate_noop_when_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    c = _cand(eng)
    eng._safe_advance_candidate(c.candidate_id, COMPARED, T1, commit=True)  # REGISTERED→COMPARED 불가
    assert eng.candidate_state(c.candidate_id) == REGISTERED


def test_safe_advance_missing_candidate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng._safe_advance_candidate("GHOST", UNDER_REVIEW, T1, commit=True)
    assert ledger.read_candidate_events() == []


def test_ingest_empty_file(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_strategies.jsonl", [])
    assert _eng().ingest_candidates("STRATEGY", T0, commit=True) == 0


def test_ingest_skips_missing_id(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_strategies.jsonl", [{"strategy_id": "ST1"}, {"other": "x"}])
    assert _eng().ingest_candidates("STRATEGY", T0, commit=True) == 1


def test_graph_and_agent_research_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    g = eng.register_candidate("research_kg", "KGE:1", "GRAPH", {}, T0, commit=True)
    ar = eng.register_candidate("agent_governance", "APP:1", "AGENT_RESEARCH", {}, T0,
                                commit=True)
    assert g.research_type == "GRAPH" and ar.research_type == "AGENT_RESEARCH"


def test_full_scenario_artifact_lineage_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.decision_intelligence.verify import lineage_validation
    eng = _eng()
    _full(eng)
    res = lineage_validation()
    assert res["ok"] is True and not res["issues"]


def test_source_ledger_map_covers_all_research_types():
    assert set(ledger.SOURCE_LEDGERS) == set(M.RESEARCH_TYPES)
