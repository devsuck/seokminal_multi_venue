"""P12.8 Research Learning Loop 테스트. **관찰·분석·기록 전용.**

학습 루프(OBSERVED→ANALYZED→LESSON_CREATED→REVIEWED→ARCHIVED)·관찰(판정)·교훈·개선 후보(applied=False·금지 자동 동사
차단)·피드백·사이클 비교·리포트(is_binding=False)·verify(체인/변조/중복/생애주기/판정/자동적용금지/참조/계보)·replay·CLI·
보안(금지import·자동 개선 없음·삭제 API 없음·불변·LEARNING≠MODIFICATION·rl_ 계층과 격리·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_learning import ledger
from jarvis.research_learning import models as M
from jarvis.research_learning.engine import ResearchLearningLoopEngine
from jarvis.research_learning.models import (
    L_ANALYZED,
    L_ARCHIVED,
    L_LESSON_CREATED,
    L_OBSERVED,
    L_REVIEWED,
    LEARNING_STATES,
    OBS_FAILED,
    OBS_INVESTIGATE,
    OBS_VERDICTS,
    OBS_WORKED,
    ForbiddenAutoActionError,
    IllegalLearningTransition,
    ImmutableLessonError,
    ImmutableLoopError,
    ImmutableObservationError,
    InvalidVerdict,
    UnknownLoopError,
)
from jarvis.research_learning.verify import (
    duplicate_integrity,
    lifecycle_integrity,
    lineage_integrity,
    no_auto_apply_integrity,
    reference_integrity,
    replay,
    verdict_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_learning.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchLearningLoopEngine()


def _loop(e, name="loop1", now=T[0]):
    return e.create_learning_cycle(name, "momentum", now, commit=True).loop_id


def _analyzed(e, lid=None):
    if lid is None:
        lid = _loop(e)
    e.observe_research(lid, "autonomous_research_pipeline", "CYC1", "sharpe up", OBS_WORKED, T[1],
                       commit=True)
    return lid


def _lesson_created(e, lid=None):
    lid = _analyzed(e, lid)
    e.extract_lesson(lid, "always oos", "validate oos", "VALIDATION", "", T[2], commit=True)
    return lid


# ══════════════ Phase 0 / 접두사 / 격리 ══════════════
def test_prefix_all_ledgers_rll():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rll_")


def test_eight_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_isolated_from_rl_layer():
    for fname, _ in ledger.ALL_LEDGERS:
        assert not (fname.startswith("rl_") and not fname.startswith("rll_"))


def test_five_lifecycle_states():
    assert len(LEARNING_STATES) == 5


def test_three_verdicts():
    assert len(OBS_VERDICTS) == 3


def test_source_read_only(tmp_path, monkeypatch):
    assert "research_experience_memory" in ledger.SOURCE_LEDGERS
    assert "decision_intelligence" in ledger.SOURCE_LEDGERS


# ══════════════ create_learning_cycle ══════════════
def test_create_cycle_genesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    assert lid.startswith("RLL:")
    assert e.current_state(lid) == L_OBSERVED


def test_create_cycle_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_learning_cycle("l", "s", T[0], commit=True)
    e.create_learning_cycle("l", "s", T[1], commit=True)
    assert len(ledger.loop_ids()) == 1


def test_create_cycle_immutable_scope(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_learning_cycle("l", "s1", T[0], commit=True)
    with pytest.raises(ImmutableLoopError):
        e.create_learning_cycle("l", "s2", T[1], commit=True)


def test_create_cycle_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_learning_cycle("l", "s", T[0], commit=False)
    assert ledger.read_loop_events() == []


# ══════════════ observe_research ══════════════
def test_observe_reaches_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e)
    assert e.current_state(lid) == L_ANALYZED


def test_observe_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    o = e.observe_research(lid, "l", "R1", "obs", OBS_WORKED, T[1], commit=True)
    assert o.observation_id.startswith("RLO:")
    assert o.verdict == OBS_WORKED


def test_observe_invalid_verdict(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    with pytest.raises(InvalidVerdict):
        e.observe_research(lid, "l", "R1", "obs", "MAYBE", T[1], commit=True)


def test_observe_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    e.observe_research(lid, "l", "R1", "obs", OBS_WORKED, T[1], commit=True)
    with pytest.raises(ImmutableObservationError):
        e.observe_research(lid, "l", "R1", "obs", OBS_FAILED, T[2], commit=True)


def test_observe_unknown_loop(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownLoopError):
        e.observe_research("RLL:ghost", "l", "R1", "o", OBS_WORKED, T[1], commit=True)


@pytest.mark.parametrize("verdict", list(OBS_VERDICTS))
def test_all_verdicts(tmp_path, monkeypatch, verdict):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    o = e.observe_research(lid, "l", "R-" + verdict, "obs", verdict, T[1], commit=True)
    assert o.verdict == verdict


def test_observe_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    e.observe_research(lid, "l", "R1", "o1", OBS_WORKED, T[1], commit=True)
    e.observe_research(lid, "l", "R2", "o2", OBS_FAILED, T[2], commit=True)
    assert len(ledger.loop_observations(lid)) == 2


# ══════════════ extract_lesson ══════════════
def test_extract_lesson_reaches_lesson_created(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _lesson_created(e)
    assert e.current_state(lid) == L_LESSON_CREATED


def test_extract_lesson_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e)
    ls = e.extract_lesson(lid, "t", "the lesson", "cat", "EV", T[2], commit=True)
    assert ls.lesson_id.startswith("RLS:")


def test_extract_lesson_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e)
    e.extract_lesson(lid, "t", "l1", "", "", T[2], commit=True)
    with pytest.raises(ImmutableLessonError):
        e.extract_lesson(lid, "t", "l2", "", "", T[3], commit=True)


def test_extract_lesson_before_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    with pytest.raises(IllegalLearningTransition):
        e.extract_lesson(lid, "t", "l", "", "", T[2], commit=True)


def test_extract_lesson_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e)
    ls = e.extract_lesson(lid, "t", "l", "", "", T[2], commit=True)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_LESSON]
    assert any(a["ref_id"] == ls.lesson_id for a in arts)


# ══════════════ record_improvement_candidate (never applied) ══════════════
def test_candidate_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    c = e.record_improvement_candidate(lid, "add reviewers", "staff up", "bottleneck", "lead", T[1],
                                       commit=True)
    assert c.improvement_id.startswith("RLI:")
    assert c.applied is False


def test_candidate_always_not_applied(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    c = e.record_improvement_candidate(lid, "t", "d", "r", "rev", T[1], commit=True)
    assert c.applied is False


@pytest.mark.parametrize("bad", ["AUTO_MODIFY_STRATEGY", "AUTO_UPDATE_MODEL",
                                 "AUTO_EXECUTE_LEARNING", "MODIFY_STRATEGY", "DEPLOY"])
def test_candidate_forbidden_auto(tmp_path, monkeypatch, bad):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    with pytest.raises(ForbiddenAutoActionError):
        e.record_improvement_candidate(lid, "t", bad, "r", "rev", T[1], commit=True)


def test_candidate_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    e.record_improvement_candidate(lid, "t", "d1", "r", "rev", T[1], commit=True)
    with pytest.raises(M.ImmutableImprovementError):
        e.record_improvement_candidate(lid, "t", "d2", "r", "rev", T[2], commit=True)


# ══════════════ record_feedback ══════════════
def test_feedback_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    f = e.record_feedback(lid, "reviewer1", "good analysis", "POSITIVE", T[1], commit=True)
    assert f.feedback_id.startswith("RLF:")
    assert f.sentiment == "POSITIVE"


def test_feedback_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    e.record_feedback(lid, "r1", "f1", "NEUTRAL", T[1], commit=True)
    e.record_feedback(lid, "r1", "f2", "NEUTRAL", T[2], commit=True)
    assert len(ledger.loop_feedback(lid)) == 2


# ══════════════ review / archive ══════════════
def test_review_reaches_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _lesson_created(e)
    e.review_loop(lid, T[5], commit=True)
    assert e.current_state(lid) == L_REVIEWED


def test_archive_from_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _lesson_created(e)
    e.review_loop(lid, T[5], commit=True)
    e.archive_loop(lid, T[6], commit=True)
    assert e.current_state(lid) == L_ARCHIVED


def test_full_lifecycle_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _lesson_created(e)
    e.review_loop(lid, T[5], commit=True)
    e.archive_loop(lid, T[6], commit=True)
    states = [ev["to_state"] for ev in ledger.loop_events(lid)]
    assert states == [L_OBSERVED, L_ANALYZED, L_LESSON_CREATED, L_REVIEWED, L_ARCHIVED]


def test_reviewed_can_reanalyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _lesson_created(e)
    e.review_loop(lid, T[5], commit=True)
    e._transition(lid, L_ANALYZED, "re", T[6], commit=True)
    assert e.current_state(lid) == L_ANALYZED


def test_archive_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _lesson_created(e)
    e.review_loop(lid, T[5], commit=True)
    e.archive_loop(lid, T[6], commit=True)
    with pytest.raises(IllegalLearningTransition):
        e.archive_loop(lid, T[7], commit=True)


# ══════════════ compare_cycles ══════════════
def test_compare_cycles(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _loop(e, "a")
    b = _loop(e, "b")
    p = e.compare_cycles(a, b, "sharpe", 1.0, 1.5, True, T[2], commit=True)
    assert p.pattern_id.startswith("RLH:")
    assert p.direction == "IMPROVED"


def test_compare_cycles_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _loop(e, "a")
    b = _loop(e, "b")
    x = e.compare_cycles(a, b, "m", 1.0, 2.0, True, T[2], commit=False)
    y = e.compare_cycles(a, b, "m", 1.0, 2.0, True, T[2], commit=False)
    assert x.pattern_id == y.pattern_id and x.delta == y.delta


def test_compare_cycles_requires_loops(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _loop(e, "a")
    with pytest.raises(UnknownLoopError):
        e.compare_cycles(a, "RLL:ghost", "m", 1.0, 2.0, True, T[2], commit=True)


# ══════════════ report ══════════════
def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e)
    e.extract_lesson(lid, "t", "l", "", "", T[2], commit=True)
    e.record_improvement_candidate(lid, "imp", "d", "r", "rev", T[3], commit=True)
    e.record_feedback(lid, "r", "f", "NEUTRAL", T[4], commit=True)
    rep = e.generate_learning_report(lid, "LOOP", T[5], commit=True)
    assert rep.observation_count == 1
    assert rep.lesson_count == 1
    assert rep.improvement_count == 1
    assert rep.feedback_count == 1


def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    rep = e.generate_learning_report(lid, "LOOP", T[1], commit=True)
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    rep = e.generate_learning_report(lid, "LOOP", T[1], commit=True)
    assert "LEARNING ≠ MODIFICATION" in rep.disclaimer


def test_report_verdict_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    e.observe_research(lid, "l", "R1", "o1", OBS_WORKED, T[1], commit=True)
    e.observe_research(lid, "l", "R2", "o2", OBS_FAILED, T[2], commit=True)
    rep = e.generate_learning_report(lid, "LOOP", T[3], commit=True)
    assert rep.verdict_distribution.get(OBS_WORKED) == 1
    assert rep.verdict_distribution.get(OBS_FAILED) == 1


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _lesson_created(e)
    e.record_improvement_candidate(lid, "imp", "d", "r", "rev", T[3], commit=True)
    e.record_feedback(lid, "r", "f", "NEUTRAL", T[4], commit=True)
    e.review_loop(lid, T[5], commit=True)
    e.generate_learning_report(lid, "LOOP", T[6], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e)
    p = ledger.state_path(ledger.OBSERVATIONS[0])
    recs = ledger.read_observations()
    recs[0]["verdict"] = OBS_INVESTIGATE
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _analyzed(e)
    p = ledger.state_path(ledger.LOOPS[0])
    recs = ledger.read_loop_events()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.LOOPS[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _loop(e)
    p = ledger.state_path(ledger.LOOPS[0])
    recs = ledger.read_loop_events()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.LOOPS[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _lesson_created(e)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    p = ledger.state_path(ledger.LOOPS[0])
    g = [r for r in ledger.loop_events(lid) if r["from_state"] == M.GENESIS][0]
    with open(p, "a") as f:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
    assert duplicate_integrity()["ok"] is False


def test_verdict_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _analyzed(e)
    p = ledger.state_path(ledger.OBSERVATIONS[0])
    recs = ledger.read_observations()
    recs[0]["verdict"] = "BOGUS"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verdict_integrity()["ok"] is False


def test_no_auto_apply_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    e.record_improvement_candidate(lid, "t", "d", "r", "rev", T[1], commit=True)
    assert no_auto_apply_integrity()["ok"] is True


def test_no_auto_apply_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    e.record_improvement_candidate(lid, "t", "d", "r", "rev", T[1], commit=True)
    p = ledger.state_path(ledger.IMPROVEMENTS[0])
    recs = ledger.read_improvements()
    recs[0]["applied"] = True  # 위조: 자동 적용됨
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert no_auto_apply_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _analyzed(e)
    assert reference_integrity()["ok"] is True


def test_reference_integrity_orphan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _analyzed(e)
    p = ledger.state_path(ledger.OBSERVATIONS[0])
    recs = ledger.read_observations()
    recs[0]["loop_id"] = "RLL:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert reference_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _loop(e)
    assert lineage_integrity()["ok"] is True


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _loop(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e)
    e.extract_lesson(lid, "t", "l", "", "", T[2], commit=True)
    s = e.summary(T[9])
    assert s.observation_count == 1
    assert s.lesson_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _loop(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _loop(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_loops_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    assert lid in e.loops_in_state(L_OBSERVED)


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (L_OBSERVED, L_ANALYZED, True),
    (L_ANALYZED, L_LESSON_CREATED, True),
    (L_LESSON_CREATED, L_REVIEWED, True),
    (L_REVIEWED, L_ARCHIVED, True),
    (L_REVIEWED, L_ANALYZED, True),
    (L_OBSERVED, L_LESSON_CREATED, False),
    (L_ANALYZED, L_REVIEWED, False),
    (L_ARCHIVED, L_ANALYZED, False),
    (L_OBSERVED, L_ARCHIVED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["AUTO_MODIFY_STRATEGY", "AUTO_UPDATE_MODEL",
                                  "AUTO_EXECUTE_LEARNING", "AUTO_MODIFY", "AUTO_DEPLOY",
                                  "MODIFY_STRATEGY", "MODIFY_MODEL", "DEPLOY"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["OBSERVE", "ANALYZE", "LEARN", "EXTRACT", "REVIEW", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.loop_id("x") == M.loop_id("x")
    assert M.lesson_id("l", "t") == M.lesson_id("l", "t")


def test_ids_prefixes_rl_scheme():
    assert M.loop_id("x").startswith("RLL:")
    assert M.loop_event_id("l", "s", 0).startswith("RLD:")
    assert M.observation_id("l", "r", "o").startswith("RLO:")
    assert M.lesson_id("l", "t").startswith("RLS:")
    assert M.improvement_id("l", "t").startswith("RLI:")
    assert M.feedback_id("l", "s", 0).startswith("RLF:")
    assert M.pattern_id("a", "b", "m").startswith("RLH:")
    assert M.report_id("l", "s", "t").startswith("RLG:")
    assert M.artifact_id("t", "r").startswith("RLA:")


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
    forbidden = ("def auto_modify_strategy", "def auto_update_model", "def auto_execute_learning",
                 "def auto_modify", "def modify_strategy", "def modify_model", "def deploy",
                 "def execute")
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
    import jarvis.research_learning.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_rll_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _lesson_created(e)
    e.record_improvement_candidate(lid, "t", "d", "r", "rev", T[3], commit=True)
    e.record_feedback(lid, "r", "f", "NEUTRAL", T[4], commit=True)
    b = _loop(e, "b")
    e.compare_cycles(lid, b, "m", 1.0, 2.0, True, T[5], commit=True)
    e.generate_learning_report(lid, "LOOP", T[6], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("rll_"), fn


def test_no_bare_rl_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _loop(e)
    for fn in os.listdir(tmp_path):
        assert not (fn.startswith("rl_") and not fn.startswith("rll_")), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("research_experience_memory", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("rxm_memories.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"memory_event_id": "M1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("research_experience_memory", "M1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_learning.__main__ import main
    assert main(["summary"]) == 0
    assert "loop_event_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_learning.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_learning.__main__ import main
    main(["cycle", "--name", "l1", "--commit"])
    lid = json.loads(capsys.readouterr().out)["loop"]["loop_id"]
    main(["observe", "--loop", lid, "--layer", "L", "--ref", "R1", "--observation", "obs",
          "--verdict", "WORKED", "--commit"])
    capsys.readouterr()
    assert main(["lesson", "--loop", lid, "--title", "t", "--lesson", "l", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["lesson"]["lesson_id"].startswith("RLS:")


def test_cli_candidate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_learning.__main__ import main
    main(["cycle", "--name", "l1", "--commit"])
    lid = json.loads(capsys.readouterr().out)["loop"]["loop_id"]
    assert main(["candidate", "--loop", lid, "--title", "t", "--desc", "d", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["candidate"]["applied"] is False


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_learning.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_learning.__main__ import main
    main(["cycle", "--name", "l1", "--commit"])
    lid = json.loads(capsys.readouterr().out)["loop"]["loop_id"]
    assert main(["report", "--loop", lid, "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["is_binding"] is False


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("st", list(LEARNING_STATES))
def test_state_membership(st):
    assert st in LEARNING_STATES


@pytest.mark.parametrize("name", ["a", "b", "c", "d"])
def test_multiple_loops(tmp_path, monkeypatch, name):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lv = e.create_learning_cycle(name, "s", T[0], commit=True)
    assert lv.name == name


@pytest.mark.parametrize("v", list(OBS_VERDICTS))
def test_report_per_verdict(tmp_path, monkeypatch, v):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e, "l-" + v)
    e.observe_research(lid, "l", "R1", "o", v, T[1], commit=True)
    rep = e.generate_learning_report(lid, "LOOP", T[2], commit=True)
    assert rep.verdict_distribution.get(v) == 1


def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_learning_cycle("l", "s", T[0], commit=False)
    assert ledger.read_loop_events() == []


def test_loop_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e, "named")
    assert e.loop_meta(lid)["name"] == "named"


def test_lesson_carries_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e)
    ls = e.extract_lesson(lid, "t", "l", "VALIDATION", "EV", T[2], commit=True)
    assert ls.category == "VALIDATION" and ls.evidence_ref == "EV"


def test_compare_direction_pure():
    assert M.compare_direction(1.0, 2.0, True)[0] == "IMPROVED"
    assert M.compare_direction(2.0, 1.0, True)[0] == "REGRESSED"
    assert M.compare_direction(1.0, 1.0, True)[0] == "UNCHANGED"


def test_verify_all_ledgers_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _loop(e)
    res = verify_chain()
    for fn, _ in ledger.ALL_LEDGERS:
        assert fn in res["ledgers"]


@pytest.mark.parametrize("i", range(8))
def test_many_observations(tmp_path, monkeypatch, i):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e, f"l{i}")
    o = e.observe_research(lid, "l", f"R{i}", f"obs{i}", OBS_WORKED, T[1], commit=True)
    assert o.source_ref == f"R{i}"


@pytest.mark.parametrize("sent", ["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"])
def test_feedback_sentiments(tmp_path, monkeypatch, sent):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e, "l-" + sent)
    f = e.record_feedback(lid, "r", "fb", sent, T[1], commit=True)
    assert f.sentiment == sent


@pytest.mark.parametrize("va,vb,exp", [(1.0, 2.0, "IMPROVED"), (2.0, 1.0, "REGRESSED"),
                                       (5.0, 5.0, "UNCHANGED")])
def test_compare_directions(tmp_path, monkeypatch, va, vb, exp):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _loop(e, f"a{va}{vb}")
    b = _loop(e, f"b{va}{vb}")
    p = e.compare_cycles(a, b, "m", va, vb, True, T[2], commit=True)
    assert p.direction == exp


@pytest.mark.parametrize("cat", ["VALIDATION", "WORKFLOW", "DATA", "MODEL", "PROCESS"])
def test_lesson_categories(tmp_path, monkeypatch, cat):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e, lid=_loop(e, "l-" + cat))
    ls = e.extract_lesson(lid, "t", "l", cat, "", T[2], commit=True)
    assert ls.category == cat


def test_compare_cycles_immutable_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _loop(e, "a")
    b = _loop(e, "b")
    e.compare_cycles(a, b, "m", 1.0, 2.0, True, T[2], commit=True)
    e.compare_cycles(a, b, "m", 1.0, 2.0, True, T[3], commit=True)
    assert len(ledger.read_patterns()) == 1


def test_observe_second_stays_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _analyzed(e)
    e.observe_research(lid, "l", "R2", "o2", OBS_FAILED, T[3], commit=True)
    assert e.current_state(lid) == L_ANALYZED
    assert len(ledger.loop_events(lid)) == 2


def test_candidate_reviewer_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    c = e.record_improvement_candidate(lid, "t", "d", "rationale here", "human_lead", T[1],
                                       commit=True)
    assert c.reviewer == "human_lead" and c.rationale == "rationale here"


def test_lesson_from_lesson_created_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _lesson_created(e)
    # LESSON_CREATED 상태에서 추가 교훈 허용
    ls = e.extract_lesson(lid, "second lesson", "l2", "", "", T[5], commit=True)
    assert ls.lesson_id.startswith("RLS:")
    assert len(ledger.loop_lessons(lid)) == 2


def test_input_digest_order():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_loop_event_id_varies_seq():
    assert M.loop_event_id("l", "ANALYZED", 0) != M.loop_event_id("l", "ANALYZED", 1)


def test_feedback_id_varies_seq():
    assert M.feedback_id("l", "s", 0) != M.feedback_id("l", "s", 1)


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []
    assert M.detect_cycle([("a", "b")]) == []


def test_list_loops(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _loop(e, "a")
    _loop(e, "b")
    assert len(e.list_loops()) == 2


def test_verdict_distribution_multi(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = _loop(e)
    e.observe_research(lid, "l", "R1", "o1", OBS_WORKED, T[1], commit=True)
    e.observe_research(lid, "l", "R2", "o2", OBS_WORKED, T[2], commit=True)
    e.observe_research(lid, "l", "R3", "o3", OBS_INVESTIGATE, T[3], commit=True)
    rep = e.generate_learning_report(lid, "LOOP", T[4], commit=True)
    assert rep.verdict_distribution.get(OBS_WORKED) == 2


def test_end_to_end_learning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    lid = e.create_learning_cycle("momentum_q3_learning", "momentum", T[0], commit=True).loop_id
    e.observe_research(lid, "autonomous_research_evaluation", "EV1", "walk-forward improved sharpe",
                       OBS_WORKED, T[1], commit=True)
    e.observe_research(lid, "autonomous_research_pipeline", "CYC9", "in-sample tuning failed",
                       OBS_FAILED, T[2], commit=True)
    e.observe_research(lid, "research_experience_memory", "M5", "regime dependence unclear",
                       OBS_INVESTIGATE, T[3], commit=True)
    e.extract_lesson(lid, "always oos validate", "walk-forward beats in-sample", "VALIDATION",
                     "EV1", T[4], commit=True)
    cand = e.record_improvement_candidate(lid, "adopt walk-forward as default",
                                          "record recommendation only", "3 observations support",
                                          "research_lead", T[5], commit=True)
    assert cand.applied is False
    e.record_feedback(lid, "senior_reviewer", "sound analysis", "POSITIVE", T[6], commit=True)
    e.review_loop(lid, T[7], commit=True)
    assert e.current_state(lid) == L_REVIEWED
    rep = e.generate_learning_report(lid, "LOOP", T[8], commit=True)
    assert rep.observation_count == 3 and rep.lesson_count == 1 and rep.improvement_count == 1
    assert verify_chain()["ok"] is True
