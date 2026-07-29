"""P10.3 Alpha Discovery & Signal Intelligence 테스트. **연구·기록 전용.**

신호 레지스트리(불변)·버전·생명주기(IDEA→...→ARCHIVED, 차단전이)·피처·가설·실험·평가(PASS/WARNING/
FAILED)·랭킹(자동선택 없음)·계보(missing feature/broken/circular)·verify(체인/변조/중복)·replay·CLI·
보안(금지import·집행/브로커 없음·기존 원장 무변경·삭제 API 없음·불변·VALIDATED≠trading·append-only).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.alpha_intelligence import ledger
from jarvis.alpha_intelligence import models as M
from jarvis.alpha_intelligence.engine import AlphaIntelligenceEngine
from jarvis.alpha_intelligence.models import (
    ARCHIVED,
    EVALUATED,
    FAILED,
    HYPOTHESIS,
    IDEA,
    PASS,
    RESEARCHING,
    VALIDATED,
    WARNING,
    IllegalTransition,
    ImmutableFeatureError,
    ImmutableSignalError,
    ImmutableVersionError,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"

_ROB_PASS = {"out_of_sample_pass": True, "walk_forward_pass": True,
             "parameter_sensitivity_pass": True, "market_regime_pass": True,
             "cost_sensitivity_pass": True}
_PERF = {"total_return": 0.3, "volatility": 0.15, "sharpe": 1.6, "max_drawdown": -0.1,
         "turnover": 1.2}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.alpha_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return AlphaIntelligenceEngine()


def _sig(eng, sid="SIG1", commit=True):
    return eng.register_signal(sid, f"{sid} name", "desc", "quant", "momentum", T0, commit=commit)


def _ver(eng, sid="SIG1", ver="1", features=None, ds="dg:D@1", commit=True):
    return eng.create_signal_version(sid, ver, "quant", "rank(mom_12_1)", {"lookback": 12},
                                     features or ["mom_12_1"], ds, T0, commit=commit)


def _flow_to_experiment(eng, sid="SIG1", ver="1", features=("mom_12_1",)):
    for fid in features:
        eng.register_feature(fid, fid, "d", "dg:D@1", "formula", "1", T0, commit=True)
    _sig(eng, sid)
    _ver(eng, sid, ver, features=list(features), commit=True)
    h = eng.create_hypothesis(sid, ver, "Momentum improves Sharpe", "prior", T0, commit=True)
    exp = eng.create_experiment(sid, ver, h.hypothesis_id, feature_dependencies=list(features),
                                dataset_version="dg:D@1", parameters={"lookback": 12},
                                evaluation_period="2015-2024", benchmark="KOSPI", now=T0,
                                commit=True)
    return exp


def _to_evaluated(eng, sid="SIG1", ver="1"):
    exp = _flow_to_experiment(eng, sid, ver)
    eng.record_evaluation(exp.experiment_id, dict(_PERF), dict(_ROB_PASS), T0, commit=True)
    return exp.experiment_id


# ── 1~17. models 순수 ──
def test_can_transition_allowed():
    assert M.can_transition("", IDEA) and M.can_transition(IDEA, HYPOTHESIS)
    assert M.can_transition(HYPOTHESIS, RESEARCHING) and M.can_transition(RESEARCHING, EVALUATED)
    assert M.can_transition(EVALUATED, VALIDATED) and M.can_transition(VALIDATED, ARCHIVED)


def test_can_transition_blocked():
    assert not M.can_transition(IDEA, RESEARCHING)
    assert not M.can_transition(HYPOTHESIS, EVALUATED)
    assert not M.can_transition(ARCHIVED, IDEA)


def test_signal_hash_deterministic():
    assert M.signal_hash("S", "n", "a", "c", "d") == M.signal_hash("S", "n", "a", "c", "d")


def test_version_hash_deterministic():
    assert M.version_hash("S", "1", "f", {"a": 1}, ["x"], "d") == M.version_hash("S", "1", "f", {"a": 1}, ["x"], "d")


def test_feature_hash_deterministic():
    assert M.feature_hash("F", "n", "ds", "form", "1") == M.feature_hash("F", "n", "ds", "form", "1")


def test_content_hash_excludes():
    a = {"x": 1, "previous_hash": "p1", "record_hash": "r1"}
    b = {"x": 1, "previous_hash": "p2", "record_hash": "r2"}
    assert M.content_hash(a) == M.content_hash(b)


def test_version_key():
    assert M.version_key("S1", "2") == "S1@2"


def test_evaluation_verdict_pass():
    assert M.evaluation_verdict(_ROB_PASS, 1.6) == PASS


def test_evaluation_verdict_failed_oos():
    assert M.evaluation_verdict(dict(_ROB_PASS, out_of_sample_pass=False), 1.6) == FAILED


def test_evaluation_verdict_failed_wf():
    assert M.evaluation_verdict(dict(_ROB_PASS, walk_forward_pass=False), 1.6) == FAILED


def test_evaluation_verdict_warning_regime():
    assert M.evaluation_verdict(dict(_ROB_PASS, market_regime_pass=False), 1.6) == WARNING


def test_evaluation_verdict_warning_low_sharpe():
    assert M.evaluation_verdict(_ROB_PASS, 0.4) == WARNING


def test_performance_score():
    assert M.performance_score(1.6) == 80 and M.performance_score(2.0) == 100


def test_robustness_score():
    assert M.robustness_score(_ROB_PASS) == 100
    assert M.robustness_score(dict(_ROB_PASS, cost_sensitivity_pass=False)) == 80


def test_stability_score():
    assert M.stability_score(-0.1, 0.0) == 70   # 100 - 30


def test_overall_score():
    assert M.overall_score(80, 100, 70) == 84   # 40+30+14


def test_detect_cycle():
    assert M.detect_cycle([("A", "B"), ("B", "A")])
    assert M.detect_cycle([("A", "B")]) == []


# ── 18~22. Signal Registry ──
def test_register_signal_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _sig(_eng(), commit=False)
    assert s.signal_id == "SIG1" and s.signal_hash.startswith("sha256:")


def test_register_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _sig(_eng())
    assert len(ledger.read_signals()) == 1


def test_register_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _sig(eng)
    assert len(ledger.read_signals()) == 1


def test_register_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng, sid="SIG1")
    with pytest.raises(ImmutableSignalError):
        eng.register_signal("SIG1", "DIFFERENT", "d", "quant", "momentum", T0, commit=True)


def test_register_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _sig(_eng())
    assert any(a["artifact_type"] == "SIGNAL" for a in ledger.read_artifacts())


# ── 23~27. Version ──
def test_create_version_idea(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    v = _ver(eng)
    assert v.to_state == IDEA and eng.current_state("SIG1@1") == IDEA


def test_version_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    assert len(ledger.read_versions()) == 1


def test_version_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    _ver(eng)
    assert len(ledger.version_events_for("SIG1@1")) == 1


def test_version_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng, features=["a"])
    with pytest.raises(ImmutableVersionError):
        _ver(eng, features=["b"])


def test_current_state_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_state("GHOST@1") == ""


# ── 28~31. Feature ──
def test_register_feature_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _eng().register_feature("mom", "Momentum", "d", "dg:D@1", "close.pct(12)", "1", T0,
                                commit=True)
    assert f.feature_id == "mom" and len(ledger.read_features()) == 1


def test_feature_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_feature("mom", "Momentum", "d", "dg:D@1", "f1", "1", T0, commit=True)
    with pytest.raises(ImmutableFeatureError):
        eng.register_feature("mom", "Momentum", "d", "dg:D@1", "f2", "1", T0, commit=True)


def test_feature_new_calc_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_feature("mom", "M", "d", "dg:D@1", "f", "1", T0, commit=True)
    eng.register_feature("mom", "M", "d", "dg:D@1", "f2", "2", T0, commit=True)
    assert len(ledger.read_features()) == 2


def test_feature_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_feature("mom", "M", "d", "dg:D@1", "f", "1", T0, commit=True)
    assert any(a["artifact_type"] == "FEATURE" for a in ledger.read_artifacts())


# ── 32~36. Hypothesis ──
def test_create_hypothesis_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    h = eng.create_hypothesis("SIG1", "1", "Momentum works", "prior", T0, commit=True)
    assert h.hypothesis_id.startswith("AHY:") and len(ledger.read_hypotheses()) == 1


def test_hypothesis_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    eng.create_hypothesis("SIG1", "1", "H", "", T0, commit=True)
    assert eng.current_state("SIG1@1") == HYPOTHESIS


def test_hypothesis_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    h = eng.create_hypothesis("SIG1", "1", "H", "", T0, commit=True)
    arts = {a["artifact_type"]: a for a in ledger.read_artifacts()}
    assert arts["HYPOTHESIS"]["parent_artifact"] == M.artifact_id("SIGNAL", "SIG1")


def test_hypothesis_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    eng.create_hypothesis("SIG1", "1", "H", "", T0, commit=True)
    assert len(ledger.read_hypotheses()) == 1


def test_hypothesis_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    eng.create_hypothesis("SIG1", "1", "H", "", T0, commit=True)
    eng.create_hypothesis("SIG1", "1", "H", "", T1, commit=True)
    assert len(ledger.read_hypotheses()) == 1


# ── 37~42. Experiment ──
def test_create_experiment_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng)
    assert exp.experiment_id.startswith("AEX:") and len(ledger.read_experiments()) == 1


def test_experiment_transitions_researching(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _flow_to_experiment(eng)
    assert eng.current_state("SIG1@1") == RESEARCHING


def test_experiment_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng).to_dict()
    for k in ("hypothesis_id", "feature_dependencies", "dataset_version", "parameters",
              "evaluation_period", "benchmark"):
        assert k in exp


def test_experiment_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng)
    arts = {a["artifact_type"]: a for a in ledger.read_artifacts()}
    assert arts["EXPERIMENT"]["parent_artifact"] == M.artifact_id("HYPOTHESIS", exp.hypothesis_id)


def test_experiment_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _flow_to_experiment(eng)
    assert len(ledger.read_experiments()) == 1


def test_experiment_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng)
    eng.create_experiment("SIG1", "1", exp.hypothesis_id, feature_dependencies=["mom_12_1"],
                          dataset_version="dg:D@1", parameters={"lookback": 12},
                          evaluation_period="2015-2024", now=T1, commit=True)
    assert len(ledger.read_experiments()) == 1


# ── 43~49. Evaluation ──
def test_record_evaluation_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng)
    ev = eng.record_evaluation(exp.experiment_id, dict(_PERF), dict(_ROB_PASS), T0, commit=True)
    assert ev.verdict == PASS


def test_record_evaluation_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng)
    ev = eng.record_evaluation(exp.experiment_id, dict(_PERF),
                               dict(_ROB_PASS, out_of_sample_pass=False), T0, commit=True)
    assert ev.verdict == FAILED


def test_record_evaluation_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng)
    ev = eng.record_evaluation(exp.experiment_id, dict(_PERF, sharpe=0.4), dict(_ROB_PASS), T0,
                               commit=True)
    assert ev.verdict == WARNING


def test_evaluation_transitions_evaluated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    assert eng.current_state("SIG1@1") == EVALUATED


def test_evaluation_metrics_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng)
    ev = eng.record_evaluation(exp.experiment_id, dict(_PERF), dict(_ROB_PASS), T0,
                               commit=True).to_dict()
    assert "performance" in ev and "robustness" in ev and ev["performance"]["sharpe"] == 1.6


def test_evaluation_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    assert any(a["artifact_type"] == "EVALUATION" for a in ledger.read_artifacts())


def test_evaluation_append_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng)
    eng.record_evaluation(exp.experiment_id, dict(_PERF), dict(_ROB_PASS), T0, commit=True)
    eng.record_evaluation(exp.experiment_id, dict(_PERF), dict(_ROB_PASS), T1, commit=True)
    assert len(ledger.read_evaluations()) == 1


# ── 50~55. Lifecycle ──
def test_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    eng.validate_signal("SIG1", "1", T0, commit=True)
    eng.archive_signal("SIG1", "1", T0, commit=True)
    assert eng.current_state("SIG1@1") == ARCHIVED


def test_validate_requires_evaluated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)   # IDEA
    with pytest.raises(IllegalTransition):
        eng.validate_signal("SIG1", "1", T0, commit=True)


def test_archive_requires_validated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)   # EVALUATED
    with pytest.raises(IllegalTransition):
        eng.archive_signal("SIG1", "1", T0, commit=True)


def test_illegal_skip_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    with pytest.raises(IllegalTransition):
        eng.transition("SIG1", "1", EVALUATED, T0, commit=True)   # IDEA→EVALUATED 차단


def test_illegal_from_archived(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    eng.validate_signal("SIG1", "1", T0, commit=True)
    eng.archive_signal("SIG1", "1", T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition("SIG1", "1", VALIDATED, T0, commit=True)


def test_validated_not_trading_enabled(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.permissions.policy import FORBIDDEN
    f0 = len(FORBIDDEN)
    eng = _eng()
    _to_evaluated(eng)
    eng.validate_signal("SIG1", "1", T0, commit=True)
    assert eng.current_state("SIG1@1") == VALIDATED
    assert len(FORBIDDEN) == f0   # VALIDATED 는 거래 권한 정책을 변경하지 않음


# ── 56~61. Ranking ──
def test_rank_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng, sid="SIG1")
    r = eng.rank_signals(T0, commit=True)
    assert len(ledger.read_rankings()) == 1 and r.rankings


def test_rank_overall_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = eng.rank_signals(T0, scores=[{"signal_id": "A", "performance_score": 80,
                                      "robustness_score": 100, "stability_score": 70}])
    assert r.rankings[0]["overall_score"] == 84 and r.rankings[0]["rank"] == 1


def test_rank_sorted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = eng.rank_signals(T0, scores=[
        {"signal_id": "A", "performance_score": 50, "robustness_score": 50, "stability_score": 50},
        {"signal_id": "B", "performance_score": 90, "robustness_score": 90, "stability_score": 90}])
    assert r.rankings[0]["signal_id"] == "B" and r.rankings[0]["rank"] == 1


def test_rank_no_auto_select(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng, sid="SIG1")
    eng.rank_signals(T0, commit=True)
    # 랭킹은 신호 상태를 변경하지 않음(자동 선택/배포 없음)
    assert eng.current_state("SIG1@1") == EVALUATED


def test_rank_from_derived_scores(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng, sid="SIG1")
    r = eng.rank_signals(T0)
    assert any(x["signal_id"] == "SIG1" for x in r.rankings)


def test_rank_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    sc = [{"signal_id": "A", "performance_score": 80, "robustness_score": 100,
           "stability_score": 70}]
    eng.rank_signals(T0, scores=sc, commit=True)
    eng.rank_signals(T1, scores=sc, commit=True)
    assert len(ledger.read_rankings()) == 1


# ── 62~65. Report ──
def test_report_signal_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng, sid="A")
    _sig(eng, sid="B")
    assert eng.generate_alpha_report(T0).signal_count == 2


def test_report_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    assert eng.generate_alpha_report(T0).state_distribution.get(EVALUATED) == 1


def test_report_evaluation_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    assert eng.generate_alpha_report(T0).evaluation_pass == 1


def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    rep = eng.generate_alpha_report(T0)
    assert rep.feature_count == 1 and rep.hypothesis_count == 1 and rep.experiment_count == 1


# ── 66~75. Verify / tamper / replay / lineage ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.verify import verify_chain
    eng = _eng()
    _to_evaluated(eng)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 5


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.verify import verify_chain
    _sig(_eng())
    path = sp("ai_signals.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["author"] = "TAMPERED"
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    assert verify_chain()["ledgers"]["ai_signals.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.verify import verify_chain
    eng = _eng()
    _sig(eng, sid="A")
    _sig(eng, sid="B")
    path = sp("ai_signals.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ledgers"]["ai_signals.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.verify import verify_chain
    _sig(_eng())
    path = sp("ai_signals.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    assert verify_chain()["ledgers"]["ai_signals.jsonl"]["reason"] in {"duplicate_id",
                                                                       "previous_hash_broken"}


def test_lineage_validation_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.verify import lineage_validation
    eng = _eng()
    _to_evaluated(eng)
    assert lineage_validation()["ok"] is True


def test_lineage_missing_feature(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.verify import lineage_validation
    eng = _eng()
    _sig(eng)
    _ver(eng, features=["ghost"])
    h = eng.create_hypothesis("SIG1", "1", "H", "", T0, commit=True)
    eng.create_experiment("SIG1", "1", h.hypothesis_id, feature_dependencies=["ghost_feature"],
                          dataset_version="dg:D@1", now=T0, commit=True)
    res = lineage_validation()
    assert res["ok"] is False and any("missing_feature" in i for i in res["issues"])


def test_lineage_invalid_dataset(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.verify import lineage_validation
    eng = _eng()
    eng.register_feature("mom_12_1", "M", "d", "dg:D@1", "f", "1", T0, commit=True)
    _sig(eng)
    _ver(eng)
    h = eng.create_hypothesis("SIG1", "1", "H", "", T0, commit=True)
    eng.create_experiment("SIG1", "1", h.hypothesis_id, feature_dependencies=["mom_12_1"],
                          dataset_version="", now=T0, commit=True)   # 데이터셋 버전 결측
    res = lineage_validation()
    assert any("invalid_dataset" in i for i in res["issues"])


def test_lineage_circular_dependency(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.verify import lineage_validation
    with open(sp("ai_artifacts.jsonl"), "w") as f:
        f.write(json.dumps({"artifact_id": "A", "parent_artifact": "B"}) + "\n")
        f.write(json.dumps({"artifact_id": "B", "parent_artifact": "A"}) + "\n")
    res = lineage_validation()
    assert res["ok"] is False and any("circular_dependency" in i for i in res["issues"])


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    from jarvis.alpha_intelligence.verify import replay
    assert replay(eng, T0)["deterministic"] is True


# ── 76~84. CLI ──
def test_cli_signal(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.__main__ import main
    rc = main(["signal", "--signal-id", "S1", "--name", "n", "--author", "a",
               "--category", "momentum", "--version", "1", "--commit"])
    assert rc == 0 and "signal" in capsys.readouterr().out


def test_cli_feature(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.__main__ import main
    rc = main(["feature", "--feature-id", "mom", "--name", "M", "--source-dataset", "dg:D@1",
               "--formula", "f", "--calc-version", "1", "--commit"])
    assert rc == 0 and "feature" in capsys.readouterr().out


def test_cli_hypothesis(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    from jarvis.alpha_intelligence.__main__ import main
    rc = main(["hypothesis", "--signal-id", "SIG1", "--version", "1", "--statement", "H",
               "--commit"])
    assert rc == 0 and "hypothesis" in capsys.readouterr().out


def test_cli_experiment(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _sig(eng)
    _ver(eng)
    h = eng.create_hypothesis("SIG1", "1", "H", "", T0, commit=True)
    from jarvis.alpha_intelligence.__main__ import main
    rc = main(["experiment", "--signal-id", "SIG1", "--version", "1",
               "--hypothesis-id", h.hypothesis_id, "--dataset-version", "dg:D@1", "--commit"])
    assert rc == 0 and "experiment" in capsys.readouterr().out


def test_cli_evaluate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    exp = _flow_to_experiment(eng)
    from jarvis.alpha_intelligence.__main__ import main
    rc = main(["evaluate", "--experiment-id", exp.experiment_id, "--sharpe", "1.6",
               "--oos", "--wf", "--param", "--regime", "--cost", "--commit"])
    assert rc == 0 and "evaluation" in capsys.readouterr().out


def test_cli_rank(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_evaluated(eng)
    from jarvis.alpha_intelligence.__main__ import main
    assert main(["rank", "--commit"]) == 0
    assert "ranking" in capsys.readouterr().out


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.__main__ import main
    assert main(["report"]) == 0
    assert "signal_count" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.alpha_intelligence.__main__ import main
    assert main(["replay"]) == 0
    assert "deterministic" in capsys.readouterr().out


# ── 85~93. 보안/충돌회피/불변 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "portfolio", _j + "broker_readonly", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.alpha_intelligence.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.alpha_intelligence.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", ".buy(", ".sell(",
                       "kill_switch(", "generate_signal_order", "execute_signal", "run_live"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_portfolio():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.alpha_intelligence.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "portfolio.",
                       "rebalance(", "allocate_capital"):
            assert banned not in src, f"{m} has broker/portfolio verb {banned}"


def test_no_autonomous_deployment():
    import importlib
    import inspect
    for m in ("engine", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.alpha_intelligence.{m}"))
        for banned in ("auto_select", "auto_deploy", "promote_to_live", "activate_signal"):
            assert banned not in src, f"{m} has autonomous verb {banned}"


def test_ledger_no_delete_api():
    import inspect
    from jarvis.alpha_intelligence import ledger as L
    src = inspect.getsource(L)
    for banned in ("def delete", "def update", "def remove", "def overwrite"):
        assert banned not in src


def test_p102_ledger_unchanged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 기존 P10.2 원장(rg_strategies)을 두고 P10.3 이 절대 건드리지 않음
    with open(sp("rg_strategies.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "legacy"}) + "\n")
    before = hashlib.sha256(open(sp("rg_strategies.jsonl"), "rb").read()).hexdigest()
    eng = _eng()
    _to_evaluated(eng)
    eng.rank_signals(T0, commit=True)
    after = hashlib.sha256(open(sp("rg_strategies.jsonl"), "rb").read()).hexdigest()
    assert before == after
    assert os.path.exists(sp("ai_signals.jsonl"))


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("alpha_intelligence", "signal_deploy", "alpha_trade"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_no_config_mutation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    import jarvis.config as cfg
    from jarvis.permissions.policy import FORBIDDEN
    a0, f0 = cfg.AUTONOMY_LEVEL, len(FORBIDDEN)
    eng = _eng()
    _to_evaluated(eng)
    eng.rank_signals(T0, commit=True)
    assert cfg.AUTONOMY_LEVEL == a0 and len(FORBIDDEN) == f0


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
