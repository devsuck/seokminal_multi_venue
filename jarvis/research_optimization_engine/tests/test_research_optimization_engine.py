"""P12.6 Research Optimization Engine 테스트. **분석·제안 전용.**

최적화 연구 생애주기(OBSERVED→ANALYZED→IDENTIFIED→PROPOSED→REVIEWED→ARCHIVED)·효율 분석·병목 탐지·역사 비교·
최적화 제안(필수 필드·금지 변경 차단)·랭킹·리포트(is_binding=False)·verify(체인/변조/중복/생애주기/제안완결성/심각도/
참조)·replay·CLI·보안(금지import·자동 최적화 없음·삭제 API 없음·불변·ANALYZE≠OPTIMIZE·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_optimization_engine import ledger
from jarvis.research_optimization_engine import models as M
from jarvis.research_optimization_engine.engine import ResearchOptimizationEngine
from jarvis.research_optimization_engine.models import (
    DIR_IMPROVED,
    DIR_REGRESSED,
    DIR_UNCHANGED,
    O_ANALYZED,
    O_ARCHIVED,
    O_IDENTIFIED,
    O_OBSERVED,
    O_PROPOSED,
    O_REVIEWED,
    SEV_CRITICAL,
    SEV_HIGH,
    SEV_LOW,
    SEV_MEDIUM,
    SEVERITIES,
    STUDY_STATES,
    ForbiddenOptimizationError,
    IllegalStudyTransition,
    ImmutableBottleneckError,
    ImmutableProposalError,
    ImmutableStudyError,
    IncompleteProposalError,
    InvalidSeverity,
    UnknownStudyError,
)
from jarvis.research_optimization_engine.verify import (
    duplicate_integrity,
    lifecycle_integrity,
    proposal_integrity,
    reference_integrity,
    replay,
    severity_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_optimization_engine.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchOptimizationEngine()


def _study(e, name="eco_study", now=T[0]):
    return e.create_optimization_study(name, "ECOSYSTEM", now, commit=True).study_id


def _analyzed(e, sid=None):
    if sid is None:
        sid = _study(e)
    e.analyze_pipeline(sid, "pipeline", "cycle_time", 12.0, 5.0, "", T[1], commit=True)
    return sid


def _identified(e, sid=None):
    sid = _analyzed(e, sid)
    e.detect_bottleneck(sid, "review_stage", SEV_HIGH, 0.9, "slow", "", T[2], commit=True)
    return sid


def _proposed(e, sid=None):
    sid = _identified(e, sid)
    e.record_proposal(sid, "parallelize review", "review is serial", "queue metrics",
                      "cut cycle time 30%", "coordination overhead", "human_reviewer", "", T[3],
                      commit=True)
    return sid


# ══════════════ Phase 0 / 접두사 / 소유 ══════════════
def test_prefix_all_ledgers_roe():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("roe_")


def test_six_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 6


def test_source_ledgers_broad(tmp_path, monkeypatch):
    for k in ("data_governance", "autonomous_research_pipeline", "autonomous_research_evaluation"):
        assert k in ledger.SOURCE_LEDGERS


def test_six_lifecycle_states():
    assert len(STUDY_STATES) == 6


def test_four_severities():
    assert len(SEVERITIES) == 4


# ══════════════ create_optimization_study ══════════════
def test_create_study_genesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    assert sid.startswith("OPS:")
    assert e.current_state(sid) == O_OBSERVED


def test_create_study_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_optimization_study("s", "ECOSYSTEM", T[0], commit=True)
    e.create_optimization_study("s", "ECOSYSTEM", T[1], commit=True)
    assert len(ledger.study_ids()) == 1


def test_create_study_immutable_scope(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_optimization_study("s", "ECOSYSTEM", T[0], commit=True)
    with pytest.raises(ImmutableStudyError):
        e.create_optimization_study("s", "PIPELINE", T[1], commit=True)


def test_create_study_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_optimization_study("s", "ECOSYSTEM", T[0], commit=False)
    assert ledger.read_study_events() == []


# ══════════════ analyze_pipeline ══════════════
def test_analyze_reaches_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    assert e.current_state(sid) == O_ANALYZED


def test_analyze_records_efficiency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    ef = e.analyze_pipeline(sid, "pipeline", "throughput", 100.0, 100.0, "", T[1], commit=True)
    assert ef.efficiency_id.startswith("OPE:")
    assert ef.value == 100.0


def test_analyze_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    e.analyze_pipeline(sid, "p", "m", 10.0, 0.0, "", T[1], commit=True)
    with pytest.raises(M.ImmutableEfficiencyError):
        e.analyze_pipeline(sid, "p", "m", 20.0, 0.0, "", T[2], commit=True)


def test_analyze_unknown_study(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownStudyError):
        e.analyze_pipeline("OPS:ghost", "p", "m", 1.0, 0.0, "", T[1], commit=True)


def test_analyze_multiple_subjects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    e.analyze_pipeline(sid, "s1", "m", 1.0, 0.0, "", T[1], commit=True)
    e.analyze_pipeline(sid, "s2", "m", 2.0, 0.0, "", T[2], commit=True)
    assert len(ledger.study_efficiency(sid)) == 2


# ══════════════ detect_bottleneck ══════════════
def test_detect_bottleneck_reaches_identified(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _identified(e)
    assert e.current_state(sid) == O_IDENTIFIED


def test_detect_bottleneck_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    b = e.detect_bottleneck(sid, "stage", SEV_CRITICAL, 0.99, "d", "EV", T[2], commit=True)
    assert b.bottleneck_id.startswith("OPB:")
    assert b.severity == SEV_CRITICAL


def test_detect_bottleneck_invalid_severity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    with pytest.raises(InvalidSeverity):
        e.detect_bottleneck(sid, "s", "BOGUS", 0.5, "", "", T[2], commit=True)


def test_detect_bottleneck_before_analysis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    # OBSERVED 상태에서 병목 탐지 불가(ANALYZED 필요)
    with pytest.raises(IllegalStudyTransition):
        e.detect_bottleneck(sid, "s", SEV_LOW, 0.1, "", "", T[2], commit=True)


def test_detect_bottleneck_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    e.detect_bottleneck(sid, "s", SEV_LOW, 0.1, "", "", T[2], commit=True)
    with pytest.raises(ImmutableBottleneckError):
        e.detect_bottleneck(sid, "s", SEV_HIGH, 0.1, "", "", T[3], commit=True)


def test_detect_multiple_bottlenecks(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    e.detect_bottleneck(sid, "s1", SEV_HIGH, 0.9, "", "", T[2], commit=True)
    e.detect_bottleneck(sid, "s2", SEV_MEDIUM, 0.5, "", "", T[3], commit=True)
    assert len(ledger.study_bottlenecks(sid)) == 2


@pytest.mark.parametrize("sev", list(SEVERITIES))
def test_all_severities(tmp_path, monkeypatch, sev):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    b = e.detect_bottleneck(sid, "s-" + sev, sev, 0.5, "", "", T[2], commit=True)
    assert b.severity == sev


def test_ranked_bottlenecks(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    e.detect_bottleneck(sid, "low_one", SEV_LOW, 0.9, "", "", T[2], commit=True)
    e.detect_bottleneck(sid, "crit_one", SEV_CRITICAL, 0.1, "", "", T[3], commit=True)
    ranked = e.ranked_bottlenecks(sid)
    # CRITICAL 이 먼저
    assert ranked[0][0] == "crit_one"


# ══════════════ compare_efficiency ══════════════
def test_compare_improved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    c = e.compare_efficiency(sid, "v1", "v2", "throughput", 100.0, 150.0, True, T[3], commit=True)
    assert c.direction == DIR_IMPROVED
    assert c.comparison_id.startswith("OPC:")


def test_compare_regressed_lower_better(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    c = e.compare_efficiency(sid, "v1", "v2", "latency", 10.0, 20.0, False, T[3], commit=True)
    assert c.direction == DIR_REGRESSED


def test_compare_unchanged(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    c = e.compare_efficiency(sid, "v1", "v2", "m", 5.0, 5.0, True, T[3], commit=True)
    assert c.direction == DIR_UNCHANGED


def test_compare_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    a = e.compare_efficiency(sid, "v1", "v2", "m", 1.0, 2.0, True, T[3], commit=False)
    b = e.compare_efficiency(sid, "v1", "v2", "m", 1.0, 2.0, True, T[3], commit=False)
    assert a.comparison_id == b.comparison_id and a.delta == b.delta


@pytest.mark.parametrize("a,b,hib,exp", [
    (1.0, 2.0, True, DIR_IMPROVED),
    (2.0, 1.0, True, DIR_REGRESSED),
    (1.0, 1.0, True, DIR_UNCHANGED),
    (2.0, 1.0, False, DIR_IMPROVED),
])
def test_compare_direction_pure(a, b, hib, exp):
    direction, _ = M.compare_direction(a, b, hib)
    assert direction == exp


# ══════════════ record_proposal ══════════════
def test_record_proposal_reaches_proposed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    assert e.current_state(sid) == O_PROPOSED


def test_record_proposal_all_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _identified(e)
    p = e.record_proposal(sid, "t", "problem", "evidence", "impact", "risk", "reviewer", "", T[3],
                          commit=True)
    assert p.proposal_id.startswith("OPP:")
    for f in ("problem", "evidence", "expected_impact", "risk", "reviewer"):
        assert getattr(p, f)


def test_record_proposal_incomplete(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _identified(e)
    with pytest.raises(IncompleteProposalError):
        e.record_proposal(sid, "t", "problem", "", "impact", "risk", "reviewer", "", T[3],
                          commit=True)


def test_record_proposal_missing_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _identified(e)
    with pytest.raises(IncompleteProposalError):
        e.record_proposal(sid, "t", "p", "e", "i", "r", "", "", T[3], commit=True)


@pytest.mark.parametrize("bad", ["CHANGE_CODE", "CHANGE_CONFIG", "CHANGE_PERMISSION",
                                 "CHANGE_STRATEGY", "AUTO_OPTIMIZE", "AUTO_DEPLOY", "DEPLOY"])
def test_record_proposal_forbidden_change(tmp_path, monkeypatch, bad):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _identified(e)
    with pytest.raises(ForbiddenOptimizationError):
        e.record_proposal(sid, "t-" + bad, "p", "e", "i", "r", "rev", bad, T[3], commit=True)


def test_record_proposal_before_identified(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    # ANALYZED 상태에서 제안 불가(IDENTIFIED 필요)
    with pytest.raises(IllegalStudyTransition):
        e.record_proposal(sid, "t", "p", "e", "i", "r", "rev", "", T[3], commit=True)


def test_record_proposal_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _identified(e)
    e.record_proposal(sid, "t", "p1", "e", "i", "r", "rev", "", T[3], commit=True)
    with pytest.raises(ImmutableProposalError):
        e.record_proposal(sid, "t", "p2", "e", "i", "r", "rev", "", T[4], commit=True)


# ══════════════ review / archive ══════════════
def test_review_reaches_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    e.review_study(sid, T[5], commit=True)
    assert e.current_state(sid) == O_REVIEWED


def test_archive_from_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    e.review_study(sid, T[5], commit=True)
    e.archive_study(sid, T[6], commit=True)
    assert e.current_state(sid) == O_ARCHIVED


def test_full_lifecycle_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    e.review_study(sid, T[5], commit=True)
    e.archive_study(sid, T[6], commit=True)
    states = [ev["to_state"] for ev in ledger.study_events(sid)]
    assert states == [O_OBSERVED, O_ANALYZED, O_IDENTIFIED, O_PROPOSED, O_REVIEWED, O_ARCHIVED]


def test_reviewed_can_reanalyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    e.review_study(sid, T[5], commit=True)
    e._transition(sid, O_ANALYZED, "re", T[6], commit=True)
    assert e.current_state(sid) == O_ANALYZED


def test_archive_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    e.review_study(sid, T[5], commit=True)
    e.archive_study(sid, T[6], commit=True)
    with pytest.raises(IllegalStudyTransition):
        e.archive_study(sid, T[7], commit=True)


# ══════════════ report ══════════════
def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    e.compare_efficiency(sid, "a", "b", "m", 1.0, 2.0, True, T[4], commit=True)
    rep = e.generate_report(sid, "STUDY", T[5], commit=True)
    assert rep.bottleneck_count == 1
    assert rep.efficiency_count == 1
    assert rep.proposal_count == 1
    assert rep.comparison_count == 1


def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    rep = e.generate_report(sid, "STUDY", T[1], commit=True)
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    rep = e.generate_report(sid, "STUDY", T[1], commit=True)
    assert "ANALYZE ≠ OPTIMIZE" in rep.disclaimer


def test_report_severity_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    e.detect_bottleneck(sid, "s1", SEV_HIGH, 0.9, "", "", T[2], commit=True)
    e.detect_bottleneck(sid, "s2", SEV_HIGH, 0.5, "", "", T[3], commit=True)
    rep = e.generate_report(sid, "STUDY", T[4], commit=True)
    assert rep.severity_distribution.get(SEV_HIGH) == 2


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    e.compare_efficiency(sid, "a", "b", "m", 1.0, 2.0, True, T[4], commit=True)
    e.review_study(sid, T[5], commit=True)
    e.generate_report(sid, "STUDY", T[6], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    e.detect_bottleneck(sid, "s", SEV_HIGH, 0.9, "", "", T[2], commit=True)
    p = ledger.state_path(ledger.BOTTLENECKS[0])
    recs = ledger.read_bottlenecks()
    recs[0]["load"] = 99.0
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _analyzed(e)
    p = ledger.state_path(ledger.STUDIES[0])
    recs = ledger.read_study_events()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.STUDIES[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _study(e)
    p = ledger.state_path(ledger.STUDIES[0])
    recs = ledger.read_study_events()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.STUDIES[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposed(e)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    p = ledger.state_path(ledger.STUDIES[0])
    g = [r for r in ledger.study_events(sid) if r["from_state"] == M.GENESIS][0]
    with open(p, "a") as f:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
    assert duplicate_integrity()["ok"] is False


def test_proposal_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _proposed(e)
    assert proposal_integrity()["ok"] is True


def test_proposal_integrity_detects_incomplete(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    p = ledger.state_path(ledger.PROPOSALS[0])
    recs = ledger.read_proposals()
    recs[0]["reviewer"] = ""
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert proposal_integrity()["ok"] is False


def test_severity_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _identified(e)
    assert severity_integrity()["ok"] is True


def test_severity_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _identified(e)
    p = ledger.state_path(ledger.BOTTLENECKS[0])
    recs = ledger.read_bottlenecks()
    recs[0]["severity"] = "BOGUS"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert severity_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _identified(e)
    assert reference_integrity()["ok"] is True


def test_reference_integrity_orphan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _identified(e)
    p = ledger.state_path(ledger.BOTTLENECKS[0])
    recs = ledger.read_bottlenecks()
    recs[0]["study_id"] = "OPS:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert reference_integrity()["ok"] is False


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _study(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _identified(e)
    s = e.summary(T[9])
    assert s.bottleneck_count == 1
    assert s.efficiency_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _study(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _study(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_studies_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    assert sid in e.studies_in_state(O_OBSERVED)


def test_list_studies(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _study(e, "a")
    e.create_optimization_study("b", "ECOSYSTEM", T[5], commit=True)
    assert len(e.list_studies()) == 2


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (O_OBSERVED, O_ANALYZED, True),
    (O_ANALYZED, O_IDENTIFIED, True),
    (O_IDENTIFIED, O_PROPOSED, True),
    (O_IDENTIFIED, O_IDENTIFIED, True),
    (O_PROPOSED, O_REVIEWED, True),
    (O_REVIEWED, O_ARCHIVED, True),
    (O_REVIEWED, O_ANALYZED, True),
    (O_OBSERVED, O_IDENTIFIED, False),
    (O_ANALYZED, O_PROPOSED, False),
    (O_ARCHIVED, O_ANALYZED, False),
    (O_PROPOSED, O_ARCHIVED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["AUTO_OPTIMIZE", "AUTO_MODIFY", "AUTO_DEPLOY", "AUTO_EXECUTE",
                                  "CHANGE_CODE", "CHANGE_CONFIG", "CHANGE_PERMISSION",
                                  "CHANGE_STRATEGY", "DEPLOY", "OPTIMIZE"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["ANALYZE", "DETECT", "COMPARE", "PROPOSE", "IDENTIFY", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.study_id("x") == M.study_id("x")
    assert M.proposal_id("s", "t") == M.proposal_id("s", "t")


def test_ids_prefixes_op_scheme():
    assert M.study_id("x").startswith("OPS:")
    assert M.study_event_id("s", "st", 0).startswith("OPV:")
    assert M.bottleneck_id("s", "t").startswith("OPB:")
    assert M.efficiency_id("s", "sub", "m").startswith("OPE:")
    assert M.proposal_id("s", "t").startswith("OPP:")
    assert M.comparison_id("s", "a", "b", "m").startswith("OPC:")
    assert M.report_id("s", "sc", "t").startswith("OPO:")


def test_severity_rank_pure():
    assert M.severity_rank(SEV_CRITICAL) > M.severity_rank(SEV_HIGH) > M.severity_rank(SEV_LOW)


def test_rank_bottlenecks_pure():
    ranked = M.rank_bottlenecks([("a", 1, 0.9), ("b", 4, 0.1), ("c", 2, 0.5)])
    assert ranked[0][0] == "b"


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p", "record_hash": "r"}
    b = {"x": 1, "previous_hash": "q", "record_hash": "s"}
    assert M.content_hash(a) == M.content_hash(b)


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []
    assert M.detect_cycle([("a", "b")]) == []


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
    forbidden = ("def auto_optimize", "def auto_modify", "def auto_deploy", "def auto_execute",
                 "def change_code", "def change_config", "def change_permission",
                 "def change_strategy", "def deploy", "def execute")
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
    import jarvis.research_optimization_engine.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_roe_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)
    e.compare_efficiency(sid, "a", "b", "m", 1.0, 2.0, True, T[4], commit=True)
    e.generate_report(sid, "STUDY", T[5], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("roe_"), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("data_governance", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("dg_datasets.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"dataset_hash": "D1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("data_governance", "D1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_optimization_engine.__main__ import main
    assert main(["summary"]) == 0
    assert "study_event_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_optimization_engine.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_optimization_engine.__main__ import main
    main(["study", "--name", "s1", "--commit"])
    sid = json.loads(capsys.readouterr().out)["study"]["study_id"]
    main(["analyze", "--study", sid, "--subject", "pipe", "--metric", "ct", "--value", "12",
          "--commit"])
    capsys.readouterr()
    main(["bottleneck", "--study", sid, "--target", "review", "--severity", "HIGH", "--commit"])
    capsys.readouterr()
    assert main(["propose", "--study", sid, "--title", "t", "--problem", "p", "--evidence", "e",
                 "--impact", "i", "--risk", "r", "--reviewer", "rev", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["proposal"]["reviewer"] == "rev"


def test_cli_compare_ranked(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_optimization_engine.__main__ import main
    main(["study", "--name", "s1", "--commit"])
    sid = json.loads(capsys.readouterr().out)["study"]["study_id"]
    main(["analyze", "--study", sid, "--subject", "p", "--metric", "m", "--value", "10",
          "--commit"])
    capsys.readouterr()
    main(["bottleneck", "--study", sid, "--target", "t1", "--severity", "CRITICAL", "--commit"])
    capsys.readouterr()
    assert main(["ranked", "--study", sid]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["ranked_bottlenecks"]) == 1


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_optimization_engine.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_optimization_engine.__main__ import main
    main(["study", "--name", "s1", "--commit"])
    sid = json.loads(capsys.readouterr().out)["study"]["study_id"]
    assert main(["report", "--study", sid, "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["is_binding"] is False


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("st", list(STUDY_STATES))
def test_state_membership(st):
    assert st in STUDY_STATES


@pytest.mark.parametrize("name", ["s1", "s2", "s3", "s4", "s5"])
def test_multiple_studies(tmp_path, monkeypatch, name):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = e.create_optimization_study(name, "ECOSYSTEM", T[0], commit=True)
    assert s.name == name


@pytest.mark.parametrize("sev", list(SEVERITIES))
def test_severity_rank_all(sev):
    assert M.severity_rank(sev) >= 1


def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_optimization_study("s", "ECOSYSTEM", T[0], commit=False)
    assert ledger.read_study_events() == []


def test_study_meta_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e, "eco")
    m = e.study_meta(sid)
    assert m["name"] == "eco" and m["scope"] == "ECOSYSTEM"


def test_study_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownStudyError):
        e.study_meta("OPS:ghost")


def test_efficiency_throughput_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    ef = e.analyze_pipeline(sid, "p", "m", 10.0, 42.0, "", T[1], commit=True)
    assert ef.throughput == 42.0


def test_bottleneck_load_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    b = e.detect_bottleneck(sid, "t", SEV_HIGH, 0.77, "d", "ev", T[2], commit=True)
    assert b.load == 0.77 and b.evidence_ref == "ev"


def test_comparison_values(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    c = e.compare_efficiency(sid, "a", "b", "m", 3.0, 7.0, True, T[3], commit=True)
    assert c.value_a == 3.0 and c.value_b == 7.0 and c.delta == 4.0


def test_proposal_carries_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _identified(e)
    p = e.record_proposal(sid, "t", "p", "e", "i", "r", "rev", "reorder review queue", T[3],
                          commit=True)
    assert p.proposed_change == "reorder review queue"


def test_verify_all_ledgers_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _study(e)
    res = verify_chain()
    for fn, _ in ledger.ALL_LEDGERS:
        assert fn in res["ledgers"]


def test_input_digest_order():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_study_event_id_varies_seq():
    assert M.study_event_id("s", "ANALYZED", 0) != M.study_event_id("s", "ANALYZED", 1)


@pytest.mark.parametrize("metric", ["cycle_time", "throughput", "latency", "queue_wait", "cost"])
def test_analyze_metrics(tmp_path, monkeypatch, metric):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e, name="s-" + metric)
    ef = e.analyze_pipeline(sid, "subj", metric, 5.0, 1.0, "", T[1], commit=True)
    assert ef.metric_name == metric


@pytest.mark.parametrize("target", ["review", "ingest", "backtest", "validation", "handoff"])
def test_bottleneck_targets(tmp_path, monkeypatch, target):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e, sid=_study(e, name="s-" + target))
    b = e.detect_bottleneck(sid, target, SEV_HIGH, 0.5, "", "", T[2], commit=True)
    assert b.target == target


@pytest.mark.parametrize("va,vb,exp", [(1.0, 2.0, DIR_IMPROVED), (2.0, 1.0, DIR_REGRESSED),
                                       (5.0, 5.0, DIR_UNCHANGED)])
def test_compare_variants(tmp_path, monkeypatch, va, vb, exp):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e, sid=_study(e, name=f"s{va}{vb}"))
    c = e.compare_efficiency(sid, "a", "b", "m", va, vb, True, T[3], commit=True)
    assert c.direction == exp


@pytest.mark.parametrize("i", range(6))
def test_efficiency_immutable_idempotent(tmp_path, monkeypatch, i):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e, name=f"s{i}")
    e.analyze_pipeline(sid, "p", "m", float(i), 0.0, "", T[1], commit=True)
    e.analyze_pipeline(sid, "p", "m", float(i), 0.0, "", T[2], commit=True)
    assert len(ledger.study_efficiency(sid)) == 1


def test_ranked_bottlenecks_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    assert e.ranked_bottlenecks(sid) == []


def test_ranked_bottlenecks_load_tiebreak(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    e.detect_bottleneck(sid, "low_load", SEV_HIGH, 0.1, "", "", T[2], commit=True)
    e.detect_bottleneck(sid, "high_load", SEV_HIGH, 0.9, "", "", T[3], commit=True)
    ranked = e.ranked_bottlenecks(sid)
    # 같은 심각도면 부하 높은 것 먼저
    assert ranked[0][0] == "high_load"


def test_compare_requires_study(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownStudyError):
        e.compare_efficiency("OPS:ghost", "a", "b", "m", 1.0, 2.0, True, T[3], commit=True)


def test_report_creates_report_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _study(e)
    rep = e.generate_report(sid, "STUDY", T[1], commit=True)
    assert ledger.report_exists(rep.report_id)


def test_comparison_immutable_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    e.compare_efficiency(sid, "a", "b", "m", 1.0, 2.0, True, T[3], commit=True)
    e.compare_efficiency(sid, "a", "b", "m", 1.0, 2.0, True, T[4], commit=True)
    assert len(ledger.read_comparisons()) == 1


def test_multiple_proposals_after_first(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _proposed(e)  # already PROPOSED after first proposal
    # 두 번째 제안(PROPOSED 상태에서도 허용)
    p2 = e.record_proposal(sid, "second", "p", "e", "i", "r", "rev", "", T[5], commit=True)
    assert p2.proposal_id.startswith("OPP:")
    assert len(ledger.study_proposals(sid)) == 2


def test_detect_bottleneck_after_identified_stays(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _identified(e)
    e.detect_bottleneck(sid, "second_bn", SEV_LOW, 0.2, "", "", T[5], commit=True)
    assert e.current_state(sid) == O_IDENTIFIED


def test_review_wrong_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    with pytest.raises(IllegalStudyTransition):
        e.review_study(sid, T[5], commit=True)


def test_study_efficiency_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s1 = _study(e, "s1")
    s2 = _study(e, "s2")
    e.analyze_pipeline(s1, "p", "m", 1.0, 0.0, "", T[1], commit=True)
    e.analyze_pipeline(s2, "p", "m", 2.0, 0.0, "", T[2], commit=True)
    assert len(ledger.study_efficiency(s1)) == 1


def test_severity_distribution_multi(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _analyzed(e)
    e.detect_bottleneck(sid, "a", SEV_LOW, 0.1, "", "", T[2], commit=True)
    e.detect_bottleneck(sid, "b", SEV_CRITICAL, 0.9, "", "", T[3], commit=True)
    rep = e.generate_report(sid, "STUDY", T[4], commit=True)
    assert rep.severity_distribution.get(SEV_LOW) == 1
    assert rep.severity_distribution.get(SEV_CRITICAL) == 1


@pytest.mark.parametrize("scope", ["ECOSYSTEM", "PIPELINE", "SCHEDULER", "AGENT"])
def test_study_scopes(tmp_path, monkeypatch, scope):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = e.create_optimization_study("s-" + scope, scope, T[0], commit=True)
    assert s.scope == scope


def test_efficiency_id_deterministic():
    assert M.efficiency_id("s", "sub", "m") == M.efficiency_id("s", "sub", "m")


def test_comparison_id_deterministic():
    assert M.comparison_id("s", "a", "b", "m") == M.comparison_id("s", "a", "b", "m")


def test_bottleneck_id_deterministic():
    assert M.bottleneck_id("s", "t") == M.bottleneck_id("s", "t")


def test_end_to_end_optimization(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = e.create_optimization_study("ecosystem_q3", "ECOSYSTEM", T[0], commit=True).study_id
    e.analyze_pipeline(sid, "pipeline", "cycle_time_h", 14.0, 6.0, "baseline", T[1], commit=True)
    e.analyze_pipeline(sid, "scheduler", "queue_wait_h", 3.0, 8.0, "", T[2], commit=True)
    e.detect_bottleneck(sid, "review_stage", SEV_CRITICAL, 0.95, "reviewers overloaded",
                        "coordinator_report", T[3], commit=True)
    e.detect_bottleneck(sid, "data_ingest", SEV_MEDIUM, 0.4, "", "", T[4], commit=True)
    e.compare_efficiency(sid, "q2", "q3", "throughput", 100.0, 130.0, True, T[5], commit=True)
    e.record_proposal(sid, "add_reviewers", "review stage bottleneck", "queue_wait metrics",
                      "cut cycle time 25%", "onboarding cost", "research_lead",
                      "propose staffing change (analysis only)", T[6], commit=True)
    e.review_study(sid, T[7], commit=True)
    assert e.current_state(sid) == O_REVIEWED
    ranked = e.ranked_bottlenecks(sid)
    assert ranked[0][0] == "review_stage"
    rep = e.generate_report(sid, "STUDY", T[8], commit=True)
    assert rep.bottleneck_count == 2 and rep.proposal_count == 1 and rep.is_binding is False
    assert verify_chain()["ok"] is True
