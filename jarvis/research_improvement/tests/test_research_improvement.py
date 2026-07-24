"""P11.10 Research Self-Improvement Loop 테스트. **연구 자기개선 — 분석·기록 전용.**

레지스트리·연구 사이클·성능 관측·프로세스 메트릭·실패 패턴(반복 실수)·개선 제안 생애주기(OBSERVED→ANALYZING→
PROPOSED→REVIEWING→ACCEPTED→ARCHIVED)·리뷰(ACCEPT/REWORK/NOTE)·학습 기록(계보·순환/dangling)·반복 비교(효율,
결정적)·리포트(is_binding=False)·아티팩트 계보·verify(체인/변조/중복/생애주기/참조누락/학습계보/아티팩트계보)·
replay·CLI·보안(금지import·실행/승인/수정 없음·삭제 API 없음·불변·IMPROVEMENT≠EXECUTION·ACCEPTED≠DEPLOYMENT·
append-only·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_improvement import ledger
from jarvis.research_improvement import models as M
from jarvis.research_improvement.engine import ResearchImprovementEngine
from jarvis.research_improvement.models import (
    CATEGORIES,
    CAT_DATA_QUALITY,
    CAT_RESEARCH_QUALITY,
    CAT_WORKFLOW_EFFICIENCY,
    DEC_ACCEPT,
    DEC_NOTE,
    DEC_REWORK,
    DIR_IMPROVED,
    DIR_REGRESSED,
    DIR_UNCHANGED,
    I_ACCEPTED,
    I_ANALYZING,
    I_ARCHIVED,
    I_OBSERVED,
    I_PROPOSED,
    I_REVIEWING,
    CircularLearningError,
    DanglingReferenceError,
    IllegalImprovementTransition,
    ImmutableCycleError,
    ImmutableFailureError,
    ImmutableImprovementError,
    ImmutableLearningError,
    ImmutableObservationError,
    InvalidCategory,
    InvalidDecision,
    MissingSourceError,
    UnknownCycleError,
    UnknownImprovementError,
    UnknownRegistryError,
)
from jarvis.research_improvement.verify import (
    duplicate_integrity,
    learning_lineage_integrity,
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
    monkeypatch.setattr("jarvis.research_improvement.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchImprovementEngine()


def _reg(e, name="improve_board", now=T[0]):
    return e.register_registry(name, "self-improve research", now, commit=True).registry_id


def _cycle(e, reg=None, name="cycle_alpha", scope="momentum", iteration=1, now=T[0]):
    if reg is None:
        reg = _reg(e, now=now)
    return e.register_cycle(reg, name, scope, iteration, now, commit=True).cycle_id


def _improvement(e, cyc=None, category=CAT_RESEARCH_QUALITY, title="tighten validation",
                 desc="add OOS split", now=T[1]):
    if cyc is None:
        cyc = _cycle(e)
    ev = e.identify_improvement(cyc, category, title, desc, now, commit=True)
    return ev.improvement_id


def _proposed(e, cyc=None):
    if cyc is None:
        cyc = _cycle(e)
    imp = _improvement(e, cyc)
    e.create_proposal(imp, "adopt walk-forward", "reduces overfit", T[2], commit=True)
    return imp


# ══════════════ Phase 0 / 네임스페이스 / 접두사 ══════════════
def test_prefix_all_ledgers_rimp():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rimp_")


def test_eleven_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 11


def test_source_ledgers_read_only_layers():
    # 13개 상위 소스 계층(READ ONLY)
    assert len(ledger.SOURCE_LEDGERS) == 13
    assert "research_conflict_resolution" in ledger.SOURCE_LEDGERS


def test_distinct_from_self_improvement_intelligence():
    # 접두사 rimp_ 는 si_ 와 구별
    for fname, _ in ledger.ALL_LEDGERS:
        assert not fname.startswith("si_")


# ══════════════ Registry ══════════════
def test_register_registry_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r1 = e.register_registry("board", "m", T[0], commit=True)
    r2 = e.register_registry("board", "m", T[0], commit=False)
    assert r1.registry_id == r2.registry_id
    assert r1.registry_id.startswith("RIG:")


def test_register_registry_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_registry("board", "m", T[0], commit=True)
    e.register_registry("board", "m", T[1], commit=True)
    assert len(ledger.read_registry()) == 1


def test_registry_not_committed_without_flag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_registry("board", "m", T[0], commit=False)
    assert ledger.read_registry() == []


# ══════════════ Cycle ══════════════
def test_register_cycle_requires_registry(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownRegistryError):
        e.register_cycle("RIG:deadbeef0000", "c", "s", 1, T[0], commit=True)


def test_register_cycle_id_and_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    assert cyc.startswith("RIC:")
    arts = [a for a in ledger.read_artifacts() if a.get("artifact_type") == M.ART_CYCLE]
    assert any(a.get("ref_id") == cyc for a in arts)


def test_register_cycle_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    e.register_cycle(reg, "c", "s", 1, T[0], commit=True)
    e.register_cycle(reg, "c", "s", 1, T[1], commit=True)
    assert len(ledger.read_cycles()) == 1


def test_register_cycle_immutable_scope(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    e.register_cycle(reg, "c", "s1", 1, T[0], commit=True)
    with pytest.raises(ImmutableCycleError):
        e.register_cycle(reg, "c", "s2", 1, T[1], commit=True)


def test_iterations_distinct_cycles(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    c1 = e.register_cycle(reg, "c", "s", 1, T[0], commit=True).cycle_id
    c2 = e.register_cycle(reg, "c", "s", 2, T[1], commit=True).cycle_id
    assert c1 != c2
    assert len(ledger.read_cycles()) == 2


# ══════════════ Observation ══════════════
def test_record_observation_requires_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownCycleError):
        e.record_observation("RIC:x", "s", "m", 1.0, now=T[0], commit=True)


def test_record_observation_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    o = e.record_observation(cyc, "sharpe", "value", 1.5, "ratio", now=T[1], commit=True)
    assert o.observation_id.startswith("RIO:")
    assert o.value == 1.5
    assert len(ledger.read_observations()) == 1


def test_record_observation_missing_source_ref(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(MissingSourceError):
        e.record_observation(cyc, "s", "m", 1.0, source_layer="research_agents", source_ref="",
                             now=T[1], commit=True)


def test_record_observation_verify_ref_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(DanglingReferenceError):
        e.record_observation(cyc, "s", "m", 1.0, source_layer="research_agents",
                             source_ref="nope", now=T[1], commit=True, verify_ref=True)


def test_record_observation_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    with pytest.raises(ImmutableObservationError):
        e.record_observation(cyc, "s", "m", 2.0, now=T[2], commit=True)


def test_record_observation_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    e.record_observation(cyc, "s", "m", 1.0, now=T[2], commit=True)
    assert len(ledger.read_observations()) == 1


def test_cycle_observations_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "a", "m", 1.0, now=T[1], commit=True)
    e.record_observation(cyc, "b", "m", 2.0, now=T[2], commit=True)
    assert len(ledger.cycle_observations(cyc)) == 2


# ══════════════ Metric ══════════════
def test_record_metric_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    m = e.record_metric(cyc, "cycle_time", 42.0, CAT_WORKFLOW_EFFICIENCY, T[1], commit=True)
    assert m.metric_id.startswith("RIM:")
    assert m.value == 42.0


def test_record_metric_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_metric(cyc, "t", 1.0, now=T[1], commit=True)
    e.record_metric(cyc, "t", 1.0, now=T[2], commit=True)
    assert len(ledger.read_metrics()) == 1


def test_record_metric_requires_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownCycleError):
        e.record_metric("RIC:x", "t", 1.0, now=T[0], commit=True)


# ══════════════ Failure patterns (repeated mistake detection) ══════════════
def test_analyze_failure_pattern_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    f = e.analyze_failure_pattern(cyc, "OVERFIT", "momentum", "reused test set", 3,
                                  now=T[1], commit=True)
    assert f.failure_id.startswith("RIF:")
    assert f.occurrences == 3


def test_analyze_failure_immutable_occurrences(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.analyze_failure_pattern(cyc, "OVERFIT", "m", "d", 2, now=T[1], commit=True)
    with pytest.raises(ImmutableFailureError):
        e.analyze_failure_pattern(cyc, "OVERFIT", "m", "d", 5, now=T[2], commit=True)


def test_analyze_failure_missing_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(MissingSourceError):
        e.analyze_failure_pattern(cyc, "T", "s", "d", 1, source_layer="research_reviewer",
                                  source_ref="", now=T[1], commit=True)


def test_analyze_failure_related_refs_sorted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    f = e.analyze_failure_pattern(cyc, "T", "s", "d", 1, related_refs=["z", "a", "a"],
                                  now=T[1], commit=True)
    assert f.related_refs == ["a", "z"]


def test_cycle_failures_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.analyze_failure_pattern(cyc, "A", "s", "d", 1, now=T[1], commit=True)
    e.analyze_failure_pattern(cyc, "B", "s", "d", 1, now=T[2], commit=True)
    assert len(ledger.cycle_failures(cyc)) == 2


# ══════════════ identify_improvement ══════════════
def test_identify_improvement_genesis_observed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    ev = e.identify_improvement(cyc, CAT_RESEARCH_QUALITY, "t", "d", T[1], commit=True)
    assert ev.to_state == I_OBSERVED
    assert ev.from_state == M.GENESIS
    assert e.current_state(ev.improvement_id) == I_OBSERVED


def test_identify_improvement_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(InvalidCategory):
        e.identify_improvement(cyc, "NOPE", "t", "d", T[1], commit=True)


def test_identify_improvement_duplicate_diff_desc(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.identify_improvement(cyc, CAT_RESEARCH_QUALITY, "t", "d1", T[1], commit=True)
    with pytest.raises(ImmutableImprovementError):
        e.identify_improvement(cyc, CAT_RESEARCH_QUALITY, "t", "d2", T[2], commit=True)


def test_identify_improvement_idempotent_same_desc(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    a = e.identify_improvement(cyc, CAT_RESEARCH_QUALITY, "t", "d", T[1], commit=True)
    b = e.identify_improvement(cyc, CAT_RESEARCH_QUALITY, "t", "d", T[2], commit=True)
    assert a.improvement_id == b.improvement_id
    assert len(ledger.read_improvement_events()) == 1


def test_improvement_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    imp = _improvement(e, cyc)
    meta = e.improvement_meta(imp)
    assert meta["state"] == I_OBSERVED
    assert meta["category"] == CAT_RESEARCH_QUALITY


def test_improvement_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownImprovementError):
        e.improvement_meta("RIP:none")


# ══════════════ create_proposal ══════════════
def test_create_proposal_reaches_proposed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _improvement(e)
    e.create_proposal(imp, "walk-forward", "less overfit", T[2], commit=True)
    assert e.current_state(imp) == I_PROPOSED


def test_create_proposal_carries_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _improvement(e)
    ev = e.create_proposal(imp, "walk-forward", "r", T[2], commit=True)
    assert ev.proposed_change == "walk-forward"


def test_create_proposal_only_from_observed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _improvement(e)
    e.create_proposal(imp, "c", "r", T[2], commit=True)
    with pytest.raises(IllegalImprovementTransition):
        e.create_proposal(imp, "c2", "r", T[3], commit=True)


def test_create_proposal_unknown_improvement(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownImprovementError):
        e.create_proposal("RIP:x", "c", "r", T[2], commit=True)


def test_proposal_records_analyzing_then_proposed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _improvement(e)
    e.create_proposal(imp, "c", "r", T[2], commit=True)
    states = [ev["to_state"] for ev in ledger.improvement_events(imp)]
    assert states == [I_OBSERVED, I_ANALYZING, I_PROPOSED]


# ══════════════ review_improvement ══════════════
def test_review_accept_reaches_accepted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    e.review_improvement(imp, "reviewer1", DEC_ACCEPT, "ok", T[3], commit=True)
    assert e.current_state(imp) == I_ACCEPTED


def test_review_accept_note_not_deployment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    e.review_improvement(imp, "r", DEC_ACCEPT, "ok", T[3], commit=True)
    accept_ev = [ev for ev in ledger.improvement_events(imp)
                 if ev["to_state"] == I_ACCEPTED][0]
    assert "NOT deployment" in accept_ev["note"]


def test_review_rework_back_to_analyzing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    e.review_improvement(imp, "r", DEC_REWORK, "redo", T[3], commit=True)
    assert e.current_state(imp) == I_ANALYZING


def test_review_note_stays_reviewing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    e.review_improvement(imp, "r", DEC_NOTE, "fyi", T[3], commit=True)
    assert e.current_state(imp) == I_REVIEWING


def test_review_invalid_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    with pytest.raises(InvalidDecision):
        e.review_improvement(imp, "r", "MAYBE", "x", T[3], commit=True)


def test_review_records_review_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    r = e.review_improvement(imp, "r", DEC_NOTE, "x", T[3], commit=True)
    assert r.review_id.startswith("RIV:")
    assert len(ledger.improvement_reviews(imp)) == 1


def test_review_rework_then_repropose(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    e.review_improvement(imp, "r", DEC_REWORK, "redo", T[3], commit=True)
    # ANALYZING → PROPOSED 재전이 가능
    e._transition(imp, I_PROPOSED, "re", T[4], commit=True)
    assert e.current_state(imp) == I_PROPOSED


def test_review_two_reviews_distinct_ids(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    r1 = e.review_improvement(imp, "r", DEC_NOTE, "a", T[3], commit=True)
    r2 = e.review_improvement(imp, "r", DEC_NOTE, "b", T[4], commit=True)
    assert r1.review_id != r2.review_id


# ══════════════ archive ══════════════
def test_archive_from_accepted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    e.review_improvement(imp, "r", DEC_ACCEPT, "ok", T[3], commit=True)
    e.archive_improvement(imp, T[4], commit=True)
    assert e.current_state(imp) == I_ARCHIVED


def test_archive_illegal_from_proposed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    with pytest.raises(IllegalImprovementTransition):
        e.archive_improvement(imp, T[4], commit=True)


# ══════════════ record_learning (lineage) ══════════════
def test_record_learning_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    lr = e.record_learning(cyc, "always OOS split", CAT_VALIDATION := "VALIDATION_PROCESS",
                           now=T[1], commit=True)
    assert lr.learning_id.startswith("RIL:")


def test_record_learning_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(InvalidCategory):
        e.record_learning(cyc, "l", "BADCAT", now=T[1], commit=True)


def test_record_learning_missing_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(MissingSourceError):
        e.record_learning(cyc, "l", source_layer="knowledge_sharing", source_ref="",
                          now=T[1], commit=True)


def test_record_learning_dangling_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(DanglingReferenceError):
        e.record_learning(cyc, "l", parent_learning="RIL:nope", now=T[1], commit=True)


def test_record_learning_immutable_parent_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    p = e.record_learning(cyc, "parent", now=T[1], commit=True).learning_id
    e.record_learning(cyc, "child", parent_learning=p, now=T[2], commit=True)
    with pytest.raises(ImmutableLearningError):
        e.record_learning(cyc, "child", parent_learning="", now=T[3], commit=True)


def test_record_learning_lineage_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    a = e.record_learning(cyc, "a", now=T[1], commit=True).learning_id
    b = e.record_learning(cyc, "b", parent_learning=a, now=T[2], commit=True).learning_id
    c = e.record_learning(cyc, "c", parent_learning=b, now=T[3], commit=True).learning_id
    assert a in e.trace_learning_lineage(c)
    assert b in e.trace_learning_lineage(c)


def test_record_learning_circular_rejected(tmp_path, monkeypatch, monkeypatch_ok=None):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    a = e.record_learning(cyc, "a", now=T[1], commit=True).learning_id
    b = e.record_learning(cyc, "b", parent_learning=a, now=T[2], commit=True).learning_id
    # a 의 부모를 b 로 만들려는 순환 시도 — a 는 이미 존재(불변)하므로 새 학습으로 우회 불가.
    # detect_cycle 직접 검증: a->b, b->a 는 순환
    assert M.detect_cycle([(a, b), (b, a)]) != []


def test_record_learning_self_cycle_via_detect():
    assert M.detect_cycle([("x", "x")]) == ["x", "x"]


# ══════════════ compare_iterations (efficiency) ══════════════
def test_compare_iterations_improved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    c1 = e.register_cycle(reg, "c", "s", 1, T[0], commit=True).cycle_id
    c2 = e.register_cycle(reg, "c", "s", 2, T[1], commit=True).cycle_id
    e.record_metric(c1, "sharpe", 1.0, now=T[2], commit=True)
    e.record_metric(c2, "sharpe", 1.5, now=T[3], commit=True)
    it = e.compare_iterations(c1, c2, "sharpe", True, T[4], commit=True)
    assert it.direction == DIR_IMPROVED
    assert it.delta == 0.5


def test_compare_iterations_regressed_lower_better(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    c1 = e.register_cycle(reg, "c", "s", 1, T[0], commit=True).cycle_id
    c2 = e.register_cycle(reg, "c", "s", 2, T[1], commit=True).cycle_id
    e.record_metric(c1, "cycle_time", 10.0, now=T[2], commit=True)
    e.record_metric(c2, "cycle_time", 20.0, now=T[3], commit=True)
    it = e.compare_iterations(c1, c2, "cycle_time", False, T[4], commit=True)
    assert it.direction == DIR_REGRESSED


def test_compare_iterations_unchanged(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    c1 = e.register_cycle(reg, "c", "s", 1, T[0], commit=True).cycle_id
    c2 = e.register_cycle(reg, "c", "s", 2, T[1], commit=True).cycle_id
    e.record_metric(c1, "m", 1.0, now=T[2], commit=True)
    e.record_metric(c2, "m", 1.0, now=T[3], commit=True)
    it = e.compare_iterations(c1, c2, "m", True, T[4], commit=True)
    assert it.direction == DIR_UNCHANGED


def test_compare_iterations_uses_observation_fallback(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    c1 = e.register_cycle(reg, "c", "s", 1, T[0], commit=True).cycle_id
    c2 = e.register_cycle(reg, "c", "s", 2, T[1], commit=True).cycle_id
    e.record_observation(c1, "sub", "ir", 0.8, now=T[2], commit=True)
    e.record_observation(c2, "sub", "ir", 1.1, now=T[3], commit=True)
    it = e.compare_iterations(c1, c2, "ir", True, T[4], commit=True)
    assert it.direction == DIR_IMPROVED


def test_compare_iterations_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    c1 = e.register_cycle(reg, "c", "s", 1, T[0], commit=True).cycle_id
    c2 = e.register_cycle(reg, "c", "s", 2, T[1], commit=True).cycle_id
    e.record_metric(c1, "m", 1.0, now=T[2], commit=True)
    e.record_metric(c2, "m", 2.0, now=T[3], commit=True)
    a = e.compare_iterations(c1, c2, "m", True, T[4], commit=True)
    b = e.compare_iterations(c1, c2, "m", True, T[5], commit=False)
    assert a.iteration_id == b.iteration_id
    assert a.delta == b.delta


def test_compare_iterations_requires_cycles(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    with pytest.raises(UnknownCycleError):
        e.compare_iterations(cyc, "RIC:none", "m", now=T[4], commit=True)


# ══════════════ compare_direction 순수함수 ══════════════
@pytest.mark.parametrize("a,b,hib,exp", [
    (1.0, 2.0, True, DIR_IMPROVED),
    (2.0, 1.0, True, DIR_REGRESSED),
    (1.0, 1.0, True, DIR_UNCHANGED),
    (2.0, 1.0, False, DIR_IMPROVED),
    (1.0, 2.0, False, DIR_REGRESSED),
    (5.0, 5.0, False, DIR_UNCHANGED),
])
def test_compare_direction_param(a, b, hib, exp):
    direction, _ = M.compare_direction(a, b, hib)
    assert direction == exp


def test_compare_direction_delta_rounding():
    _, delta = M.compare_direction(1.0, 1.123456789, True)
    assert delta == 0.12345679


# ══════════════ generate_report ══════════════
def test_generate_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    e.analyze_failure_pattern(cyc, "T", "s", "d", 1, now=T[2], commit=True)
    imp = _improvement(e, cyc, title="x", desc="d")
    e.create_proposal(imp, "c", "r", T[3], commit=True)
    e.review_improvement(imp, "r", DEC_ACCEPT, "ok", T[4], commit=True)
    e.record_learning(cyc, "lesson", now=T[5], commit=True)
    rep = e.generate_report(cyc, "CYCLE", T[6], commit=True)
    assert rep.observation_count == 1
    assert rep.failure_count == 1
    assert rep.proposal_count == 1
    assert rep.accepted_count == 1
    assert rep.learning_count == 1


def test_generate_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    rep = e.generate_report(cyc, "CYCLE", T[1], commit=True)
    assert rep.is_binding is False
    assert rep.process_acceptance_only is True


def test_generate_report_category_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.identify_improvement(cyc, CAT_RESEARCH_QUALITY, "a", "d", T[1], commit=True)
    e.identify_improvement(cyc, CAT_DATA_QUALITY, "b", "d", T[2], commit=True)
    rep = e.generate_report(cyc, "CYCLE", T[3], commit=True)
    assert rep.category_distribution.get(CAT_RESEARCH_QUALITY) == 1
    assert rep.category_distribution.get(CAT_DATA_QUALITY) == 1


def test_generate_report_disclaimer_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    rep = e.generate_report(cyc, "CYCLE", T[1], commit=True)
    assert "IMPROVEMENT ≠ EXECUTION" in rep.disclaimer


def test_generate_report_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    rep = e.generate_report(cyc, "CYCLE", T[1], commit=True)
    arts = [a for a in ledger.read_artifacts() if a.get("artifact_type") == M.ART_REPORT]
    assert any(a.get("ref_id") == rep.report_id for a in arts)


# ══════════════ Hash chain & tamper ══════════════
def test_chain_intact_after_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    imp = _improvement(e, cyc, title="x")
    e.create_proposal(imp, "c", "r", T[2], commit=True)
    e.review_improvement(imp, "r", DEC_ACCEPT, "ok", T[3], commit=True)
    res = verify_chain()
    assert res["ok"] is True


def test_verify_detects_tampered_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    p = ledger.state_path(ledger.OBSERVATIONS[0])
    recs = ledger.read_observations()
    recs[0]["value"] = 999.0
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    res = verify_chain()
    assert res["ok"] is False


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    e.register_cycle(reg, "c1", "s", 1, T[0], commit=True)
    e.register_cycle(reg, "c2", "s", 1, T[1], commit=True)
    p = ledger.state_path(ledger.CYCLES[0])
    recs = ledger.read_cycles()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    res = verify_chain()
    assert res["ledgers"][ledger.CYCLES[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    p = ledger.state_path(ledger.OBSERVATIONS[0])
    recs = ledger.read_observations()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    res = verify_chain()
    assert res["ledgers"][ledger.OBSERVATIONS[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    e.review_improvement(imp, "r", DEC_ACCEPT, "ok", T[3], commit=True)
    assert lifecycle_integrity()["ok"] is True


def test_lifecycle_integrity_bad_initial(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    # 수동으로 잘못된 초기 상태 이벤트 주입
    p = ledger.state_path(ledger.PROPOSALS[0])
    bad = {"improvement_event_id": "RIE:bad", "improvement_id": "RIP:bad", "cycle_id": cyc,
           "from_state": M.GENESIS, "to_state": I_PROPOSED, "previous_hash": M.GENESIS}
    bad["record_hash"] = M.content_hash(bad)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps(bad, ensure_ascii=False) + "\n")
    assert lifecycle_integrity()["ok"] is False


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _improvement(e)
    assert duplicate_integrity()["ok"] is True


def test_duplicate_integrity_detects_dup_genesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    imp = _improvement(e, cyc, title="x")
    p = ledger.state_path(ledger.PROPOSALS[0])
    recs = ledger.read_improvement_events()
    g = [r for r in recs if r["improvement_id"] == imp and r["from_state"] == M.GENESIS][0]
    with open(p, "a") as f:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
    assert duplicate_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, "u", "research_agents", "ref1", now=T[1], commit=True)
    assert reference_integrity()["ok"] is True


def test_reference_integrity_detects_missing_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    # 관측을 손상시켜 source_layer 만 채운다
    p = ledger.state_path(ledger.OBSERVATIONS[0])
    recs = ledger.read_observations()
    recs[0]["source_layer"] = "research_agents"
    recs[0]["source_ref"] = ""
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert reference_integrity()["ok"] is False


def test_learning_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    a = e.record_learning(cyc, "a", now=T[1], commit=True).learning_id
    e.record_learning(cyc, "b", parent_learning=a, now=T[2], commit=True)
    assert learning_lineage_integrity()["ok"] is True


def test_learning_lineage_detects_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    a = e.record_learning(cyc, "a", now=T[1], commit=True).learning_id
    e.record_learning(cyc, "b", parent_learning=a, now=T[2], commit=True)
    # 부모를 삭제된 것으로 위조
    p = ledger.state_path(ledger.LEARNING[0])
    recs = ledger.read_learning()
    recs[1]["parent_learning"] = "RIL:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert learning_lineage_integrity()["ok"] is False


def test_learning_lineage_detects_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    a = e.record_learning(cyc, "a", now=T[1], commit=True).learning_id
    b = e.record_learning(cyc, "b", parent_learning=a, now=T[2], commit=True).learning_id
    p = ledger.state_path(ledger.LEARNING[0])
    recs = ledger.read_learning()
    # a 의 부모를 b 로 위조 → 순환
    for r in recs:
        if r["learning_id"] == a:
            r["parent_learning"] = b
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert learning_lineage_integrity()["ok"] is False


def test_lineage_integrity_artifacts_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _improvement(e, cyc)
    assert lineage_integrity()["ok"] is True


def test_lineage_integrity_detects_dangling_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    _improvement(e, cyc)
    p = ledger.state_path(ledger.ARTIFACTS[0])
    recs = ledger.read_artifacts()
    for r in recs:
        if r.get("parent_artifact"):
            r["parent_artifact"] = "RIA:ghost"
            break
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert lineage_integrity()["ok"] is False


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    res = replay(e, T[9])
    assert res["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    e.record_metric(cyc, "t", 2.0, now=T[2], commit=True)
    e.analyze_failure_pattern(cyc, "T", "s", "d", 1, now=T[3], commit=True)
    s = e.summary(T[9])
    assert s.cycle_count == 1
    assert s.observation_count == 1
    assert s.metric_count == 1
    assert s.failure_count == 1


def test_replay_rebuild_via_reengine(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


# ══════════════ list / query helpers ══════════════
def test_list_cycles(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    e.register_cycle(reg, "a", "s", 1, T[0], commit=True)
    e.register_cycle(reg, "b", "s", 1, T[1], commit=True)
    assert len(e.list_cycles(reg)) == 2


def test_improvements_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    assert imp in e.improvements_in_state(I_PROPOSED)


def test_improvements_of(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    imp = _improvement(e, cyc)
    assert imp in e.improvements_of(cyc)


# ══════════════ can_transition 매트릭스 ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (I_OBSERVED, I_ANALYZING, True),
    (I_ANALYZING, I_PROPOSED, True),
    (I_PROPOSED, I_REVIEWING, True),
    (I_REVIEWING, I_ACCEPTED, True),
    (I_REVIEWING, I_ANALYZING, True),
    (I_ACCEPTED, I_ARCHIVED, True),
    (I_OBSERVED, I_ACCEPTED, False),
    (I_OBSERVED, I_PROPOSED, False),
    (I_ARCHIVED, I_ACCEPTED, False),
    (I_ACCEPTED, I_PROPOSED, False),
    (I_PROPOSED, I_ACCEPTED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "APPROVE_STRATEGY",
                                  "APPROVE_MODEL", "PROMOTE_LIVE", "MODIFY_PERMISSION",
                                  "MODIFY_CONFIG", "approve", " deploy "])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["OBSERVE", "ANALYZE", "RECORD", "IDENTIFY", "REVIEW", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 ══════════════
def test_ids_deterministic():
    assert M.registry_id("x") == M.registry_id("x")
    assert M.cycle_id("r", "n", 1) == M.cycle_id("r", "n", 1)
    assert M.improvement_id("c", "cat", "t") == M.improvement_id("c", "cat", "t")
    assert M.learning_id("c", "l") == M.learning_id("c", "l")


def test_ids_prefixes():
    assert M.registry_id("x").startswith("RIG:")
    assert M.cycle_id("r", "n", 1).startswith("RIC:")
    assert M.observation_id("c", "s", "m").startswith("RIO:")
    assert M.metric_id("c", "m").startswith("RIM:")
    assert M.failure_id("c", "p", "s").startswith("RIF:")
    assert M.improvement_id("c", "cat", "t").startswith("RIP:")
    assert M.improvement_event_id("i", "s", 0).startswith("RIE:")
    assert M.learning_id("c", "l").startswith("RIL:")
    assert M.iteration_id("a", "b", "m").startswith("RIT:")
    assert M.review_id("i", "r", 0).startswith("RIV:")
    assert M.report_id("c", "s", "t").startswith("RIR:")
    assert M.artifact_id("t", "r").startswith("RIA:")


def test_event_id_varies_with_seq():
    assert M.improvement_event_id("i", "ANALYZING", 0) != M.improvement_event_id("i", "ANALYZING", 1)


# ══════════════ content_hash / input_digest ══════════════
def test_content_hash_excludes_hash_fields():
    rec = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    rec2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(rec) == M.content_hash(rec2)


def test_content_hash_changes_with_content():
    assert M.content_hash({"a": 1}) != M.content_hash({"a": 2})


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


# ══════════════ ancestors / detect_cycle 순수함수 ══════════════
def test_ancestors_transitive():
    edges = [("c", "b"), ("b", "a")]
    assert M.ancestors(edges, "c") == ["a", "b"]


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_detect_cycle_found():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []


# ══════════════ 보안: 금지 import AST 스캔 ══════════════
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
    offenders = []
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
    forbidden = ("def execute", "def trade", "def deploy", "def allocate", "def approve_strategy",
                 "def approve_model", "def promote_live", "def modify_permission",
                 "def modify_config", "def place_order")
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
    import jarvis.research_improvement.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    src_path = os.path.join(_PKG_DIR, "ledger.py")
    with open(src_path) as f:
        src = f.read()
    # 쓰기 모드는 append("a") 만 허용
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing_file(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("research_agents", "x") is False


def test_source_ref_exists_unknown_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("nonexistent_layer", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    # 소스 원장 파일을 만들고 읽기만 하는지 확인
    p = ledger.state_path("ragt_reports.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"report_id": "R1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("research_agents", "R1") is True
    assert os.path.getmtime(p) == before


# ══════════════ verify_chain empty ══════════════
def test_verify_chain_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] == 0


def test_verify_integrity_engine_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cycle(e)
    assert e.verify_integrity()["ok"] is True


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_improvement.__main__ import main
    assert main(["summary"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "cycle_count" in out


def test_cli_registry_and_cycle(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_improvement.__main__ import main
    assert main(["registry", "--name", "b", "--commit"]) == 0
    reg = json.loads(capsys.readouterr().out)["registry"]["registry_id"]
    assert main(["cycle", "--registry", reg, "--name", "c", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["cycle"]["cycle_id"].startswith("RIC:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_improvement.__main__ import main
    assert main(["verify"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_improvement.__main__ import main
    main(["registry", "--name", "b", "--commit"])
    reg = json.loads(capsys.readouterr().out)["registry"]["registry_id"]
    main(["cycle", "--registry", reg, "--name", "c", "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    main(["identify", "--cycle", cyc, "--category", CAT_RESEARCH_QUALITY, "--title", "t",
          "--desc", "d", "--commit"])
    imp = json.loads(capsys.readouterr().out)["improvement"]["improvement_id"]
    assert main(["propose", "--improvement", imp, "--change", "walk-forward", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == I_PROPOSED
    assert main(["review", "--improvement", imp, "--reviewer", "r", "--decision", "ACCEPT",
                 "--commit"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_improvement.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


def test_cli_compare(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_improvement.__main__ import main
    main(["registry", "--name", "b", "--commit"])
    reg = json.loads(capsys.readouterr().out)["registry"]["registry_id"]
    main(["cycle", "--registry", reg, "--name", "c", "--iteration", "1", "--commit"])
    c1 = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    main(["cycle", "--registry", reg, "--name", "c", "--iteration", "2", "--commit"])
    c2 = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    main(["metric", "--cycle", c1, "--metric", "m", "--value", "1.0", "--commit"])
    capsys.readouterr()
    main(["metric", "--cycle", c2, "--metric", "m", "--value", "2.0", "--commit"])
    capsys.readouterr()
    assert main(["compare", "--cycle-a", c1, "--cycle-b", c2, "--metric", "m"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["iteration"]["direction"] == DIR_IMPROVED


def test_cli_learn_and_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_improvement.__main__ import main
    main(["registry", "--name", "b", "--commit"])
    reg = json.loads(capsys.readouterr().out)["registry"]["registry_id"]
    main(["cycle", "--registry", reg, "--name", "c", "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    assert main(["learn", "--cycle", cyc, "--lesson", "OOS split", "--commit"]) == 0
    capsys.readouterr()
    assert main(["report", "--cycle", cyc, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


# ══════════════ 카테고리/상태/결정 상수 ══════════════
def test_categories_count():
    assert len(CATEGORIES) == 7


def test_improvement_states_count():
    assert len(M.IMPROVEMENT_STATES) == 6


def test_decisions_count():
    assert len(M.DECISIONS) == 3


@pytest.mark.parametrize("cat", list(CATEGORIES))
def test_identify_all_categories(tmp_path, monkeypatch, cat):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    ev = e.identify_improvement(cyc, cat, "t-" + cat, "d", T[1], commit=True)
    assert ev.category == cat


# ══════════════ 불변: 재등록 무변경 ══════════════
def test_registry_reregister_same_returns_existing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r1 = e.register_registry("b", "m", T[0], commit=True)
    r2 = e.register_registry("b", "different", T[1], commit=True)
    # id 는 name 만으로 결정 → 동일, 최초 mandate 보존
    assert r1.registry_id == r2.registry_id
    assert ledger.get_registry(r1.registry_id)["mandate"] == "m"


def test_no_stray_state_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    reg = _reg(e)
    e.register_cycle(reg, "c", "s", 1, T[0], commit=False)
    assert ledger.read_cycles() == []


# ══════════════ 리포트 accepted_count with archived ══════════════
def test_report_accepted_count_includes_archived(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    imp = _improvement(e, cyc, title="x")
    e.create_proposal(imp, "c", "r", T[2], commit=True)
    e.review_improvement(imp, "r", DEC_ACCEPT, "ok", T[3], commit=True)
    e.archive_improvement(imp, T[4], commit=True)
    rep = e.generate_report(cyc, "CYCLE", T[5], commit=True)
    assert rep.accepted_count == 1


# ══════════════ event sourcing: re-entry ANALYZING via REWORK ══════════════
def test_rework_reentry_analyzing_event_ids_distinct(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    imp = _proposed(e)
    e.review_improvement(imp, "r", DEC_REWORK, "redo", T[3], commit=True)
    evs = ledger.improvement_events(imp)
    ids = [ev["improvement_event_id"] for ev in evs]
    assert len(ids) == len(set(ids))  # 재진입에도 이벤트 id 유일


def test_full_lifecycle_states_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    imp = _improvement(e, cyc, title="x")
    e.create_proposal(imp, "c", "r", T[2], commit=True)
    e.review_improvement(imp, "r", DEC_ACCEPT, "ok", T[3], commit=True)
    e.archive_improvement(imp, T[4], commit=True)
    states = [ev["to_state"] for ev in ledger.improvement_events(imp)]
    assert states == [I_OBSERVED, I_ANALYZING, I_PROPOSED, I_REVIEWING, I_ACCEPTED, I_ARCHIVED]


# ══════════════ regression: no stray files & prefix isolation ══════════════
def test_all_written_files_have_rimp_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cycle(e)
    e.record_observation(cyc, "s", "m", 1.0, now=T[1], commit=True)
    imp = _improvement(e, cyc, title="x")
    e.create_proposal(imp, "c", "r", T[2], commit=True)
    e.record_learning(cyc, "l", now=T[3], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("rimp_"), fn
