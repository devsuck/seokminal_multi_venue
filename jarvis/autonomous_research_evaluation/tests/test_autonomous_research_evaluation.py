"""P12.5 Autonomous Research Evaluation 테스트. **평가·기록 전용.**

기준 정의·평가(CREATED→EVALUATING→SCORED→REVIEWED→ARCHIVED)·6 차원 점수·가중 종합·벤치마크 비교(결정적)·품질
리포트(is_approval=False)·verify(체인/변조/중복/생애주기/차원/참조/계보)·replay·CLI·보안(금지import·승인/배포/선택 없음·
삭제 API 없음·불변·SCORE≠APPROVAL·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.autonomous_research_evaluation import ledger
from jarvis.autonomous_research_evaluation import models as M
from jarvis.autonomous_research_evaluation.engine import AutonomousResearchEvaluationEngine
from jarvis.autonomous_research_evaluation.models import (
    DIM_EFFICIENCY,
    DIM_EVIDENCE_STRENGTH,
    DIM_KNOWLEDGE_CONTRIBUTION,
    DIM_REPRODUCIBILITY,
    DIM_RESEARCH_QUALITY,
    DIM_ROBUSTNESS,
    E_ARCHIVED,
    E_CREATED,
    E_EVALUATING,
    E_REVIEWED,
    E_SCORED,
    EVAL_DIMENSIONS,
    EVAL_STATES,
    IllegalEvalTransition,
    ImmutableCriterionError,
    ImmutableScoreError,
    InvalidDimension,
    UnknownEvaluationError,
)
from jarvis.autonomous_research_evaluation.verify import (
    dimension_integrity,
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
    monkeypatch.setattr("jarvis.autonomous_research_evaluation.ledger.state_path", sp)
    return sp


def _eng():
    return AutonomousResearchEvaluationEngine()


def _evaluation(e, layer="autonomous_research_pipeline", ref="CYC1", now=T[0]):
    return e.evaluate_cycle(layer, ref, now, commit=True).evaluation_id


def _scored(e, ev=None):
    if ev is None:
        ev = _evaluation(e)
    e.score_quality(ev, DIM_RESEARCH_QUALITY, 0.8, "", "", T[1], commit=True)
    e.score_quality(ev, DIM_REPRODUCIBILITY, 0.6, "", "", T[2], commit=True)
    e.finalize_scoring(ev, T[3], commit=True)
    return ev


# ══════════════ Phase 0 / 접두사 / 소유 ══════════════
def test_prefix_all_ledgers_are():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("are_")


def test_six_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 6


def test_source_includes_p10_7_and_p12(tmp_path, monkeypatch):
    assert "decision_intelligence" in ledger.SOURCE_LEDGERS
    assert "adaptive_research_loop" in ledger.SOURCE_LEDGERS


def test_six_dimensions():
    assert len(EVAL_DIMENSIONS) == 6


def test_five_lifecycle_states():
    assert len(EVAL_STATES) == 5


# ══════════════ define_metric ══════════════
def test_define_metric_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = e.define_metric("sharpe_quality", DIM_RESEARCH_QUALITY, 2.0, "d", T[0], commit=True)
    assert c.criterion_id.startswith("EVM:")
    assert c.weight == 2.0


def test_define_metric_invalid_dimension(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(InvalidDimension):
        e.define_metric("x", "BOGUS", 1.0, "", T[0], commit=True)


def test_define_metric_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.define_metric("m", DIM_EFFICIENCY, 1.0, "", T[0], commit=True)
    with pytest.raises(ImmutableCriterionError):
        e.define_metric("m", DIM_EFFICIENCY, 2.0, "", T[1], commit=True)


@pytest.mark.parametrize("dim", list(EVAL_DIMENSIONS))
def test_define_metric_all_dimensions(tmp_path, monkeypatch, dim):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = e.define_metric("m-" + dim, dim, 1.0, "", T[0], commit=True)
    assert c.dimension == dim


# ══════════════ evaluate_cycle ══════════════
def test_evaluate_cycle_genesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    assert ev.startswith("EVG:")
    assert e.current_state(ev) == E_EVALUATING


def test_evaluate_cycle_records_created_then_evaluating(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    states = [x["to_state"] for x in ledger.evaluation_events(ev)]
    assert states == [E_CREATED, E_EVALUATING]


def test_evaluate_cycle_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.evaluate_cycle("l", "R1", T[0], commit=True)
    e.evaluate_cycle("l", "R1", T[1], commit=True)
    assert len(ledger.evaluation_events(a.evaluation_id)) == 2


def test_evaluate_cycle_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_EVALUATION]
    assert any(a["ref_id"] == ev for a in arts)


# ══════════════ score_quality ══════════════
def test_score_quality_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    s = e.score_quality(ev, DIM_RESEARCH_QUALITY, 0.9, "EVID1", "strong", T[1], commit=True)
    assert s.score_id.startswith("EVS:")
    assert s.score == 0.9


def test_score_quality_invalid_dimension(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    with pytest.raises(InvalidDimension):
        e.score_quality(ev, "BOGUS", 0.5, "", "", T[1], commit=True)


def test_score_quality_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_EFFICIENCY, 0.5, "", "", T[1], commit=True)
    with pytest.raises(ImmutableScoreError):
        e.score_quality(ev, DIM_EFFICIENCY, 0.9, "", "", T[2], commit=True)


def test_score_quality_wrong_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    # SCORED 상태에서 추가 점수 불가
    with pytest.raises(IllegalEvalTransition):
        e.score_quality(ev, DIM_ROBUSTNESS, 0.5, "", "", T[5], commit=True)


def test_score_quality_unknown_evaluation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownEvaluationError):
        e.score_quality("EVG:ghost", DIM_EFFICIENCY, 0.5, "", "", T[1], commit=True)


@pytest.mark.parametrize("dim", list(EVAL_DIMENSIONS))
def test_score_all_dimensions(tmp_path, monkeypatch, dim):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    s = e.score_quality(ev, dim, 0.7, "", "", T[1], commit=True)
    assert s.dimension == dim


# ══════════════ finalize_scoring (weighted overall) ══════════════
def test_finalize_reaches_scored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    assert e.current_state(ev) == E_SCORED


def test_finalize_overall_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_RESEARCH_QUALITY, 0.8, "", "", T[1], commit=True)
    e.score_quality(ev, DIM_REPRODUCIBILITY, 0.4, "", "", T[2], commit=True)
    e.finalize_scoring(ev, T[3], commit=True)
    # 균등 가중 평균 = 0.6
    assert e.overall_score(ev) == 0.6


def test_finalize_weighted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.define_metric("rq", DIM_RESEARCH_QUALITY, 3.0, "", T[0], commit=True)
    e.define_metric("rp", DIM_REPRODUCIBILITY, 1.0, "", T[0], commit=True)
    ev = e.evaluate_cycle("l", "R1", T[0], commit=True).evaluation_id
    e.score_quality(ev, DIM_RESEARCH_QUALITY, 1.0, "", "", T[1], commit=True)
    e.score_quality(ev, DIM_REPRODUCIBILITY, 0.0, "", "", T[2], commit=True)
    e.finalize_scoring(ev, T[3], commit=True)
    # (1.0*3 + 0.0*1) / 4 = 0.75
    assert e.overall_score(ev) == 0.75


def test_weighted_score_pure():
    assert M.weighted_score({"a": 1.0, "b": 0.0}, {}) == 0.5
    assert M.weighted_score({}, {}) == 0.0
    assert M.weighted_score({"a": 1.0, "b": 0.0}, {"a": 3.0, "b": 1.0}) == 0.75


# ══════════════ review / archive ══════════════
def test_review_reaches_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    e.review_evaluation(ev, "human", T[5], commit=True)
    assert e.current_state(ev) == E_REVIEWED


def test_review_note_score_not_approval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    r = e.review_evaluation(ev, "human", T[5], commit=True)
    assert "SCORE≠APPROVAL" in r.note


def test_archive_from_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    e.review_evaluation(ev, "h", T[5], commit=True)
    e.archive_evaluation(ev, T[6], commit=True)
    assert e.current_state(ev) == E_ARCHIVED


def test_full_lifecycle_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    e.review_evaluation(ev, "h", T[5], commit=True)
    e.archive_evaluation(ev, T[6], commit=True)
    states = [x["to_state"] for x in ledger.evaluation_events(ev)]
    assert states == [E_CREATED, E_EVALUATING, E_SCORED, E_REVIEWED, E_ARCHIVED]


def test_reviewed_can_reevaluate(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    e.review_evaluation(ev, "h", T[5], commit=True)
    e._transition(ev, E_EVALUATING, 0.0, "re", T[6], commit=True)
    assert e.current_state(ev) == E_EVALUATING


def test_archive_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    e.review_evaluation(ev, "h", T[5], commit=True)
    e.archive_evaluation(ev, T[6], commit=True)
    with pytest.raises(IllegalEvalTransition):
        e.archive_evaluation(ev, T[7], commit=True)


# ══════════════ compare_research (benchmark) ══════════════
def test_compare_overall(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _evaluation(e, ref="A")
    e.score_quality(a, DIM_RESEARCH_QUALITY, 0.5, "", "", T[1], commit=True)
    e.finalize_scoring(a, T[2], commit=True)
    b = e.evaluate_cycle("l", "B", T[3], commit=True).evaluation_id
    e.score_quality(b, DIM_RESEARCH_QUALITY, 0.9, "", "", T[4], commit=True)
    e.finalize_scoring(b, T[5], commit=True)
    bench = e.compare_research(a, b, "overall", T[6], commit=True)
    assert bench.winner == "B"


def test_compare_by_dimension(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _evaluation(e, ref="A")
    e.score_quality(a, DIM_ROBUSTNESS, 0.9, "", "", T[1], commit=True)
    b = e.evaluate_cycle("l", "B", T[2], commit=True).evaluation_id
    e.score_quality(b, DIM_ROBUSTNESS, 0.3, "", "", T[3], commit=True)
    bench = e.compare_research(a, b, DIM_ROBUSTNESS, T[4], commit=True)
    assert bench.winner == "A"


def test_compare_tie(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _evaluation(e, ref="A")
    b = e.evaluate_cycle("l", "B", T[1], commit=True).evaluation_id
    bench = e.compare_research(a, b, "overall", T[2], commit=True)
    assert bench.winner == "TIE"


def test_compare_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _evaluation(e, ref="A")
    b = e.evaluate_cycle("l", "B", T[1], commit=True).evaluation_id
    x = e.compare_research(a, b, "overall", T[2], commit=False)
    y = e.compare_research(a, b, "overall", T[2], commit=False)
    assert x.benchmark_id == y.benchmark_id and x.delta == y.delta


def test_compare_requires_evaluations(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _evaluation(e)
    with pytest.raises(UnknownEvaluationError):
        e.compare_research(a, "EVG:ghost", "overall", T[2], commit=True)


@pytest.mark.parametrize("a,b,exp", [(0.5, 0.9, "B"), (0.9, 0.3, "A"), (0.5, 0.5, "TIE")])
def test_compare_direction_pure(a, b, exp):
    winner, _ = M.compare_direction(a, b)
    assert winner == exp


# ══════════════ report ══════════════
def test_report_not_approval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _scored(e)
    rep = e.generate_quality_report("ALL", "ALL", T[9], commit=True)
    assert rep.is_approval is False
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rep = e.generate_quality_report("ALL", "ALL", T[1], commit=True)
    assert "SCORE ≠ APPROVAL" in rep.disclaimer


def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    e.review_evaluation(ev, "h", T[5], commit=True)
    rep = e.generate_quality_report("ALL", "ALL", T[9], commit=True)
    assert rep.evaluation_count == 1
    assert rep.scored_count == 1
    assert rep.reviewed_count == 1


def test_report_dimension_averages(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_RESEARCH_QUALITY, 0.8, "", "", T[1], commit=True)
    rep = e.generate_quality_report("ALL", "ALL", T[9], commit=True)
    assert rep.dimension_averages.get(DIM_RESEARCH_QUALITY) == 0.8


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.define_metric("m", DIM_EFFICIENCY, 1.0, "", T[0], commit=True)
    ev = _scored(e)
    e.review_evaluation(ev, "h", T[5], commit=True)
    b = e.evaluate_cycle("l", "B", T[6], commit=True).evaluation_id
    e.compare_research(ev, b, "overall", T[7], commit=True)
    e.generate_quality_report("ALL", "ALL", T[8], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_EFFICIENCY, 0.5, "", "", T[1], commit=True)
    p = ledger.state_path(ledger.SCORES[0])
    recs = ledger.read_scores()
    recs[0]["score"] = 9.99
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _evaluation(e)
    p = ledger.state_path(ledger.REGISTRY[0])
    recs = ledger.read_evaluation_events()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.REGISTRY[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _evaluation(e)
    p = ledger.state_path(ledger.REGISTRY[0])
    recs = ledger.read_evaluation_events()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.REGISTRY[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _scored(e)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    p = ledger.state_path(ledger.REGISTRY[0])
    g = [r for r in ledger.evaluation_events(ev) if r["from_state"] == M.GENESIS][0]
    with open(p, "a") as f:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
    assert duplicate_integrity()["ok"] is False


def test_dimension_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_EFFICIENCY, 0.5, "", "", T[1], commit=True)
    assert dimension_integrity()["ok"] is True


def test_dimension_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_EFFICIENCY, 0.5, "", "", T[1], commit=True)
    p = ledger.state_path(ledger.SCORES[0])
    recs = ledger.read_scores()
    recs[0]["dimension"] = "BOGUS"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert dimension_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_EFFICIENCY, 0.5, "", "", T[1], commit=True)
    assert reference_integrity()["ok"] is True


def test_reference_integrity_orphan_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_EFFICIENCY, 0.5, "", "", T[1], commit=True)
    p = ledger.state_path(ledger.SCORES[0])
    recs = ledger.read_scores()
    recs[0]["evaluation_id"] = "EVG:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert reference_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _evaluation(e)
    assert lineage_integrity()["ok"] is True


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _evaluation(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_EFFICIENCY, 0.5, "", "", T[1], commit=True)
    s = e.summary(T[9])
    assert s.score_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _evaluation(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _evaluation(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_evaluations_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    assert ev in e.evaluations_in_state(E_EVALUATING)


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (E_CREATED, E_EVALUATING, True),
    (E_EVALUATING, E_SCORED, True),
    (E_SCORED, E_REVIEWED, True),
    (E_REVIEWED, E_ARCHIVED, True),
    (E_REVIEWED, E_EVALUATING, True),
    (E_CREATED, E_SCORED, False),
    (E_EVALUATING, E_REVIEWED, False),
    (E_ARCHIVED, E_EVALUATING, False),
    (E_SCORED, E_ARCHIVED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["APPROVE_LIVE", "DEPLOY", "SELECT_STRATEGY", "ALLOCATE_CAPITAL",
                                  "APPROVE", "PROMOTE", "execute", "trade"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["EVALUATE", "SCORE", "MEASURE", "BENCHMARK", "COMPARE", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.evaluation_id("l", "r") == M.evaluation_id("l", "r")
    assert M.score_id("e", "d") == M.score_id("e", "d")


def test_ids_prefixes_ev_scheme():
    assert M.evaluation_id("l", "r").startswith("EVG:")
    assert M.evaluation_event_id("e", "s", 0).startswith("EVR:")
    assert M.criterion_id("n").startswith("EVM:")
    assert M.score_id("e", "d").startswith("EVS:")
    assert M.benchmark_id("a", "b", "m").startswith("EVB:")
    assert M.report_id("s", "i", "t").startswith("EVO:")
    assert M.artifact_id("t", "r").startswith("EVL:")


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
    forbidden = ("def approve_live", "def deploy", "def select_strategy", "def allocate_capital",
                 "def approve", "def promote", "def execute")
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
    import jarvis.autonomous_research_evaluation.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_are_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.define_metric("m", DIM_EFFICIENCY, 1.0, "", T[0], commit=True)
    ev = _scored(e)
    b = e.evaluate_cycle("l", "B", T[6], commit=True).evaluation_id
    e.compare_research(ev, b, "overall", T[7], commit=True)
    e.generate_quality_report("ALL", "ALL", T[8], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("are_"), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("decision_intelligence", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("di_frameworks.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"framework_id": "F1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("decision_intelligence", "F1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_evaluation.__main__ import main
    assert main(["summary"]) == 0
    assert "score_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_evaluation.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_evaluation.__main__ import main
    main(["evaluate", "--layer", "l", "--ref", "R1", "--commit"])
    ev = json.loads(capsys.readouterr().out)["evaluation"]["evaluation_id"]
    main(["score", "--evaluation", ev, "--dimension", DIM_RESEARCH_QUALITY, "--score", "0.8",
          "--commit"])
    capsys.readouterr()
    assert main(["finalize", "--evaluation", ev, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == E_SCORED


def test_cli_compare(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_evaluation.__main__ import main
    main(["evaluate", "--layer", "l", "--ref", "A", "--commit"])
    a = json.loads(capsys.readouterr().out)["evaluation"]["evaluation_id"]
    main(["score", "--evaluation", a, "--dimension", DIM_ROBUSTNESS, "--score", "0.9", "--commit"])
    capsys.readouterr()
    main(["evaluate", "--layer", "l", "--ref", "B", "--commit"])
    b = json.loads(capsys.readouterr().out)["evaluation"]["evaluation_id"]
    assert main(["compare", "--eval-a", a, "--eval-b", b, "--metric", DIM_ROBUSTNESS,
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["benchmark"]["winner"] == "A"


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_evaluation.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_report_metric(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_evaluation.__main__ import main
    assert main(["metric", "--name", "m", "--dimension", DIM_EFFICIENCY, "--commit"]) == 0
    capsys.readouterr()
    assert main(["report", "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["is_approval"] is False


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("st", list(EVAL_STATES))
def test_state_membership(st):
    assert st in EVAL_STATES


@pytest.mark.parametrize("ref", ["R1", "R2", "R3", "R4", "R5"])
def test_multiple_evaluations(tmp_path, monkeypatch, ref):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.evaluate_cycle("l", ref, T[0], commit=True)
    assert ev.research_ref == ref


def test_dimension_scores_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_EFFICIENCY, 0.7, "", "", T[1], commit=True)
    assert e.dimension_scores(ev)[DIM_EFFICIENCY] == 0.7


def test_evaluation_meta_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e, ref="XYZ")
    m = e.evaluation_meta(ev)
    assert m["research_ref"] == "XYZ"


def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.evaluate_cycle("l", "R1", T[0], commit=False)
    assert ledger.read_evaluation_events() == []


def test_benchmark_immutable_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _evaluation(e, ref="A")
    b = e.evaluate_cycle("l", "B", T[1], commit=True).evaluation_id
    e.compare_research(a, b, "overall", T[2], commit=True)
    e.compare_research(a, b, "overall", T[3], commit=True)
    assert len(ledger.read_benchmarks()) == 1


def test_score_evidence_rationale(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    s = e.score_quality(ev, DIM_EVIDENCE_STRENGTH, 0.9, "EVID_X", "strong evidence", T[1],
                        commit=True)
    assert s.evidence_ref == "EVID_X" and s.rationale == "strong evidence"


def test_dimension_averages_multi_eval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _evaluation(e, ref="A")
    e.score_quality(a, DIM_KNOWLEDGE_CONTRIBUTION, 0.4, "", "", T[1], commit=True)
    b = e.evaluate_cycle("l", "B", T[2], commit=True).evaluation_id
    e.score_quality(b, DIM_KNOWLEDGE_CONTRIBUTION, 0.6, "", "", T[3], commit=True)
    rep = e.generate_quality_report("ALL", "ALL", T[4], commit=True)
    assert rep.dimension_averages.get(DIM_KNOWLEDGE_CONTRIBUTION) == 0.5


@pytest.mark.parametrize("dim", list(EVAL_DIMENSIONS))
def test_report_each_dimension(tmp_path, monkeypatch, dim):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e, ref=f"R-{dim}")
    e.score_quality(ev, dim, 0.5, "", "", T[1], commit=True)
    rep = e.generate_quality_report("ALL", "ALL", T[2], commit=True)
    assert dim in rep.dimension_averages


@pytest.mark.parametrize("w", [0.5, 1.0, 2.0, 3.0])
def test_metric_weights(tmp_path, monkeypatch, w):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = e.define_metric(f"m{w}", DIM_EFFICIENCY, w, "", T[0], commit=True)
    assert c.weight == w


@pytest.mark.parametrize("sc", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_various_scores(tmp_path, monkeypatch, sc):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e, ref=f"R{sc}")
    s = e.score_quality(ev, DIM_EFFICIENCY, sc, "", "", T[1], commit=True)
    assert s.score == sc


def test_finalize_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownEvaluationError):
        e.finalize_scoring("EVG:ghost", T[3], commit=True)


def test_criterion_dimension_weights_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.define_metric("m", DIM_ROBUSTNESS, 4.0, "", T[0], commit=True)
    assert ledger.dimension_weights()[DIM_ROBUSTNESS] == 4.0


def test_scored_count_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _scored(e)
    rep = e.generate_quality_report("ALL", "ALL", T[9], commit=True)
    assert rep.scored_count == 1


def test_report_scope_evaluation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _scored(e)
    rep = e.generate_quality_report(ev, "EVALUATION", T[9], commit=True)
    assert rep.evaluation_count == 1


def test_report_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rep = e.generate_quality_report("ALL", "ALL", T[1], commit=True)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_REPORT]
    assert any(a["ref_id"] == rep.report_id for a in arts)


def test_overall_score_zero_before_finalize(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = _evaluation(e)
    e.score_quality(ev, DIM_EFFICIENCY, 0.9, "", "", T[1], commit=True)
    # finalize 전 overall 은 0.0
    assert e.overall_score(ev) == 0.0


def test_input_digest_order():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_eval_event_id_varies_seq():
    assert M.evaluation_event_id("e", "SCORED", 0) != M.evaluation_event_id("e", "SCORED", 1)


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []
    assert M.detect_cycle([("a", "b")]) == []


def test_list_evaluations(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _evaluation(e, ref="A")
    e.evaluate_cycle("l", "B", T[5], commit=True)
    assert len(e.list_evaluations()) == 2


def test_verify_all_ledgers_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _evaluation(e)
    res = verify_chain()
    for fn, _ in ledger.ALL_LEDGERS:
        assert fn in res["ledgers"]


def test_benchmark_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _evaluation(e, ref="A")
    e.score_quality(a, DIM_EFFICIENCY, 0.3, "", "", T[1], commit=True)
    e.finalize_scoring(a, T[2], commit=True)
    b = e.evaluate_cycle("l", "B", T[3], commit=True).evaluation_id
    e.score_quality(b, DIM_EFFICIENCY, 0.7, "", "", T[4], commit=True)
    e.finalize_scoring(b, T[5], commit=True)
    bench = e.compare_research(a, b, "overall", T[6], commit=True)
    assert bench.value_a == 0.3 and bench.value_b == 0.7


def test_end_to_end_evaluation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.define_metric("quality", DIM_RESEARCH_QUALITY, 2.0, "core", T[0], commit=True)
    ev = e.evaluate_cycle("autonomous_research_pipeline", "CYC_momentum", T[1],
                          commit=True).evaluation_id
    e.score_quality(ev, DIM_RESEARCH_QUALITY, 0.9, "backtest", "robust", T[2], commit=True)
    e.score_quality(ev, DIM_REPRODUCIBILITY, 0.8, "rerun", "consistent", T[3], commit=True)
    e.score_quality(ev, DIM_EVIDENCE_STRENGTH, 0.7, "oos", "strong", T[4], commit=True)
    e.score_quality(ev, DIM_EFFICIENCY, 0.6, "runtime", "ok", T[5], commit=True)
    e.score_quality(ev, DIM_ROBUSTNESS, 0.85, "stress", "stable", T[6], commit=True)
    e.score_quality(ev, DIM_KNOWLEDGE_CONTRIBUTION, 0.5, "novel", "some", T[7], commit=True)
    e.finalize_scoring(ev, T[8], commit=True)
    e.review_evaluation(ev, "senior_reviewer", T[9], commit=True)
    assert e.current_state(ev) == E_REVIEWED
    assert 0.0 <= e.overall_score(ev) <= 1.0
    rep = e.generate_quality_report("ALL", "ALL", T[10], commit=True)
    assert rep.evaluation_count == 1 and rep.is_approval is False
    assert verify_chain()["ok"] is True
