"""P10.2 Strategy Research & Experiment Governance 테스트. **연구 관리 전용.**

전략 레지스트리(불변)·버전·생명주기(DRAFT→...→ARCHIVED, 차단전이)·가설·실험·백테스트·검증(6체크,
PASS/WARNING/FAILED)·비교(추천 기록만)·아티팩트 계보·verify(체인/변조/중복/계보)·replay·CLI·보안
(금지import·집행/브로커 없음·자동승인 없음·기존 원장 무변경·삭제 API 없음·불변·append-only·
VALIDATED≠permission).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.research_governance import ledger
from jarvis.research_governance import models as M
from jarvis.research_governance.engine import ResearchGovernanceEngine
from jarvis.research_governance.models import (
    ARCHIVED,
    BACKTESTED,
    DRAFT,
    FAILED,
    PASS,
    RESEARCHING,
    REVIEWED,
    VALIDATED,
    WARNING,
    IllegalTransition,
    ImmutableStrategyError,
    ImmutableVersionError,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"

_PASS_CHECKS = {"out_of_sample_pass": True, "walk_forward_pass": True,
                "cost_sensitivity_pass": True, "parameter_robustness_pass": True,
                "benchmark_outperforms": True, "overfitting_warning": False}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_governance.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchGovernanceEngine()


def _strat(eng, sid="S1", commit=True):
    return eng.register_strategy(sid, f"{sid} name", "desc", "quant", "equity", T0, commit=commit)


def _ver(eng, sid="S1", ver="1", params=None, commit=True):
    return eng.create_version(sid, ver, "quant", params or {"lookback": 12}, "dg:D@1",
                              "rd:F@1", "mg:M@1", T0, commit=commit)


def _exp(eng, sid="S1", ver="1", hyp="Momentum improves Sharpe", commit=True):
    return eng.create_experiment(sid, ver, hyp, parameters={"lookback": 12},
                                 backtest_period="2015-2024", benchmark="KOSPI",
                                 cost_assumption={"bps": 10}, now=T0, commit=commit)


def _to_backtested(eng, sid="S1", ver="1"):
    _strat(eng, sid)
    _ver(eng, sid, ver)
    exp = _exp(eng, sid, ver)
    eng.record_backtest(exp.experiment_id, sharpe=1.4, total_return=0.3, volatility=0.15,
                        max_drawdown=-0.1, turnover=1.2, now=T0, commit=True)
    return exp.experiment_id


# ── 1~16. models 순수 ──
def test_can_transition_allowed():
    assert M.can_transition("", DRAFT) and M.can_transition(DRAFT, RESEARCHING)
    assert M.can_transition(RESEARCHING, BACKTESTED) and M.can_transition(BACKTESTED, VALIDATED)
    assert M.can_transition(VALIDATED, REVIEWED) and M.can_transition(REVIEWED, ARCHIVED)


def test_can_transition_blocked():
    assert not M.can_transition(DRAFT, VALIDATED)
    assert not M.can_transition(RESEARCHING, REVIEWED)
    assert not M.can_transition(ARCHIVED, DRAFT)


def test_strategy_hash_deterministic():
    assert M.strategy_hash("S", "n", "a", "eq", "d") == M.strategy_hash("S", "n", "a", "eq", "d")


def test_version_hash_deterministic():
    assert M.version_hash("S", "1", {"a": 1}, "d", "f", "m") == M.version_hash("S", "1", {"a": 1}, "d", "f", "m")


def test_content_hash_excludes():
    a = {"x": 1, "previous_hash": "p1", "record_hash": "r1"}
    b = {"x": 1, "previous_hash": "p2", "record_hash": "r2"}
    assert M.content_hash(a) == M.content_hash(b)


def test_version_key():
    assert M.version_key("S1", "2") == "S1@2"


def test_validation_status_pass():
    assert M.validation_status(_PASS_CHECKS) == PASS


def test_validation_status_failed_oos():
    c = dict(_PASS_CHECKS, out_of_sample_pass=False)
    assert M.validation_status(c) == FAILED


def test_validation_status_failed_wf():
    c = dict(_PASS_CHECKS, walk_forward_pass=False)
    assert M.validation_status(c) == FAILED


def test_validation_status_warning_overfit():
    c = dict(_PASS_CHECKS, overfitting_warning=True)
    assert M.validation_status(c) == WARNING


def test_validation_status_warning_cost():
    c = dict(_PASS_CHECKS, cost_sensitivity_pass=False)
    assert M.validation_status(c) == WARNING


def test_comparison_recommendation_a():
    assert M.comparison_recommendation(1.5, 1.0) == M.A_PREFERRED


def test_comparison_recommendation_b():
    assert M.comparison_recommendation(1.0, 1.5) == M.B_PREFERRED


def test_comparison_recommendation_inconclusive():
    assert M.comparison_recommendation(1.0, 1.05) == M.INCONCLUSIVE


def test_artifact_id_deterministic():
    assert M.artifact_id("EXPERIMENT", "E1") == M.artifact_id("EXPERIMENT", "E1")


def test_hypothesis_id():
    assert M.hypothesis_id("S", "stmt").startswith("HYP:")


# ── 17~21. Strategy Registry ──
def test_register_strategy_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _strat(_eng(), commit=False)
    assert s.strategy_id == "S1" and s.strategy_hash.startswith("sha256:")


def test_register_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _strat(_eng())
    assert len(ledger.read_strategies()) == 1


def test_register_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _strat(eng)
    assert len(ledger.read_strategies()) == 1


def test_register_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng, sid="S1")
    with pytest.raises(ImmutableStrategyError):
        eng.register_strategy("S1", "DIFFERENT", "d", "quant", "equity", T0, commit=True)


def test_register_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _strat(_eng())
    arts = ledger.read_artifacts()
    assert any(a["artifact_type"] == "STRATEGY" for a in arts)


# ── 22~26. Version ──
def test_create_version_draft(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    v = _ver(eng)
    assert v.to_state == DRAFT and eng.current_state("S1@1") == DRAFT


def test_version_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    assert len(ledger.read_versions()) == 1


def test_version_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    _ver(eng)
    assert len(ledger.version_events_for("S1@1")) == 1


def test_version_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng, params={"lookback": 12})
    with pytest.raises(ImmutableVersionError):
        _ver(eng, params={"lookback": 99})


def test_current_state_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_state("GHOST@1") == ""


# ── 27~34. Experiment / Hypothesis ──
def test_create_experiment_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    exp = _exp(eng)
    assert exp.experiment_id.startswith("EXP:") and len(ledger.read_experiments()) == 1


def test_experiment_transitions_researching(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    _exp(eng)
    assert eng.current_state("S1@1") == RESEARCHING


def test_experiment_embeds_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    exp = _exp(eng, hyp="Value beats growth")
    assert exp.hypothesis == "Value beats growth" and exp.hypothesis_id.startswith("HYP:")


def test_experiment_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    exp = _exp(eng).to_dict()
    for k in ("dataset_version", "feature_version", "model_version", "parameters",
              "backtest_period", "cost_assumption", "benchmark"):
        assert k in exp


def test_experiment_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    exp = _exp(eng)
    arts = {a["artifact_type"]: a for a in ledger.read_artifacts()}
    assert "EXPERIMENT" in arts
    assert arts["EXPERIMENT"]["parent_artifact"] == M.artifact_id("STRATEGY", "S1")


def test_experiment_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    _exp(eng)
    assert len(ledger.read_experiments()) == 1


def test_experiment_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    _exp(eng)
    _exp(eng)
    assert len(ledger.read_experiments()) == 1


def test_hypothesis_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _eng().hypothesis("S1", "Momentum works", "prior evidence", T0)
    assert h.statement == "Momentum works" and h.strategy_id == "S1"


# ── 35~40. Backtest ──
def test_record_backtest_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    exp = _exp(eng)
    b = eng.record_backtest(exp.experiment_id, sharpe=1.4, now=T0, commit=True)
    assert b.sharpe == 1.4 and len(ledger.read_backtests()) == 1


def test_backtest_transitions_backtested(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_backtested(eng)
    assert eng.current_state("S1@1") == BACKTESTED


def test_backtest_metrics(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    exp = _exp(eng)
    b = eng.record_backtest(exp.experiment_id, total_return=0.3, volatility=0.15, sharpe=1.4,
                            max_drawdown=-0.1, turnover=1.2, benchmark_comparison={"kospi": 0.05},
                            now=T0, commit=True).to_dict()
    for k in ("total_return", "volatility", "sharpe", "max_drawdown", "turnover",
              "benchmark_comparison"):
        assert k in b


def test_backtest_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    arts = {a["artifact_type"]: a for a in ledger.read_artifacts()}
    assert arts["BACKTEST"]["parent_artifact"] == M.artifact_id("EXPERIMENT", eid)


def test_backtest_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_backtested(eng)
    assert len(ledger.read_backtests()) == 1


def test_backtest_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    exp = _exp(eng)
    eng.record_backtest(exp.experiment_id, sharpe=1.4, now=T0, commit=True)
    eng.record_backtest(exp.experiment_id, sharpe=1.4, now=T1, commit=True)
    assert len(ledger.read_backtests()) == 1


# ── 41~48. Validation ──
def test_record_validation_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    r = eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    assert r.validation_status == PASS


def test_record_validation_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    r = eng.record_validation(eid, dict(_PASS_CHECKS, out_of_sample_pass=False), T0, commit=True)
    assert r.validation_status == FAILED


def test_record_validation_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    r = eng.record_validation(eid, dict(_PASS_CHECKS, overfitting_warning=True), T0, commit=True)
    assert r.validation_status == WARNING


def test_validation_transitions_validated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    assert eng.current_state("S1@1") == VALIDATED


def test_validation_is_not_trading_permission(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.permissions.policy import FORBIDDEN
    f0 = len(FORBIDDEN)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    # VALIDATED 는 연구 상태 — 실제 거래 권한 정책 무변경
    assert len(FORBIDDEN) == f0


def test_validation_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    assert any(a["artifact_type"] == "VALIDATION" for a in ledger.read_artifacts())


def test_validation_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    assert len(ledger.read_validations()) == 1


def test_validation_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    eng.record_validation(eid, _PASS_CHECKS, T1, commit=True)
    assert len(ledger.read_validations()) == 1


# ── 49~53. Lifecycle ──
def test_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    eng.review_strategy("S1", "1", T0, commit=True)
    eng.archive_strategy("S1", "1", T0, commit=True)
    assert eng.current_state("S1@1") == ARCHIVED


def test_review_requires_validated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)   # DRAFT
    with pytest.raises(IllegalTransition):
        eng.review_strategy("S1", "1", T0, commit=True)


def test_archive_requires_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)   # VALIDATED
    with pytest.raises(IllegalTransition):
        eng.archive_strategy("S1", "1", T0, commit=True)


def test_illegal_transition_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    with pytest.raises(IllegalTransition):
        eng.transition("S1", "1", VALIDATED, T0, commit=True)   # DRAFT→VALIDATED 차단


def test_illegal_from_archived(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    eng.review_strategy("S1", "1", T0, commit=True)
    eng.archive_strategy("S1", "1", T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition("S1", "1", REVIEWED, T0, commit=True)


# ── 54~58. Comparison ──
def _two_experiments(eng):
    _strat(eng, sid="S1")
    _ver(eng, sid="S1", ver="1")
    e1 = eng.create_experiment("S1", "1", "H1", parameters={"a": 1}, backtest_period="p1",
                               now=T0, commit=True)
    eng.record_backtest(e1.experiment_id, sharpe=1.6, now=T0, commit=True)
    _strat(eng, sid="S2")
    _ver(eng, sid="S2", ver="1")
    e2 = eng.create_experiment("S2", "1", "H2", parameters={"a": 2}, backtest_period="p1",
                               now=T0, commit=True)
    eng.record_backtest(e2.experiment_id, sharpe=1.0, now=T0, commit=True)
    return e1.experiment_id, e2.experiment_id


def test_compare_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_experiments(eng)
    c = eng.compare_experiments(a, b, T0, commit=True)
    assert len(ledger.read_comparisons()) == 1 and c.comparison_id.startswith("CMP:")


def test_compare_deltas(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_experiments(eng)
    c = eng.compare_experiments(a, b, T0)
    assert round(c.deltas["sharpe"], 2) == 0.6


def test_compare_recommendation_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_experiments(eng)
    c = eng.compare_experiments(a, b, T0)
    assert c.recommendation == M.A_PREFERRED   # 추천 라벨 기록만


def test_compare_no_auto_select(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_experiments(eng)
    eng.compare_experiments(a, b, T0, commit=True)
    # 비교는 전략 상태를 변경하지 않음(자동 선택/승인 없음)
    assert eng.current_state("S1@1") == BACKTESTED
    assert eng.current_state("S2@1") == BACKTESTED


def test_compare_append_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_experiments(eng)
    eng.compare_experiments(a, b, T0, commit=True)
    eng.compare_experiments(a, b, T1, commit=True)
    assert len(ledger.read_comparisons()) == 1


# ── 59~62. Report ──
def test_report_strategy_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng, sid="S1")
    _strat(eng, sid="S2")
    assert eng.generate_research_report(T0).strategy_count == 2


def test_report_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_backtested(eng)
    rep = eng.generate_research_report(T0)
    assert rep.state_distribution.get(BACKTESTED) == 1


def test_report_validation_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    assert eng.generate_research_report(T0).validation_pass == 1


def test_report_experiment_backtest_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_backtested(eng)
    rep = eng.generate_research_report(T0)
    assert rep.experiment_count == 1 and rep.backtest_count == 1


# ── 63~70. Verify / tamper / replay / artifact ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.verify import verify_chain
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 4


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.verify import verify_chain
    _strat(_eng())
    path = sp("rg_strategies.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["author"] = "TAMPERED"
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    assert verify_chain()["ledgers"]["rg_strategies.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.verify import verify_chain
    eng = _eng()
    _strat(eng, sid="S1")
    _strat(eng, sid="S2")
    path = sp("rg_strategies.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ledgers"]["rg_strategies.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.verify import verify_chain
    _strat(_eng())
    path = sp("rg_strategies.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    assert verify_chain()["ledgers"]["rg_strategies.jsonl"]["reason"] in {"duplicate_id",
                                                                          "previous_hash_broken"}


def test_verify_artifact_linkage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.verify import artifact_linkage
    eng = _eng()
    _to_backtested(eng)
    assert artifact_linkage()["ok"] is True


def test_verify_artifact_dangling_parent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.verify import artifact_linkage
    with open(sp("rg_artifacts.jsonl"), "w") as f:
        f.write(json.dumps({"artifact_id": "ART:child", "parent_artifact": "ART:ghost"}) + "\n")
    res = artifact_linkage()
    assert res["ok"] is False and res["reason"] == "dangling_parent"


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_backtested(eng)
    from jarvis.research_governance.verify import replay
    assert replay(eng, T0)["deterministic"] is True


# ── 71~78. CLI ──
def test_cli_strategy(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.__main__ import main
    rc = main(["strategy", "--strategy-id", "S1", "--name", "n", "--author", "a",
               "--asset-class", "equity", "--version", "1", "--commit"])
    assert rc == 0 and "strategy" in capsys.readouterr().out


def test_cli_experiment(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    from jarvis.research_governance.__main__ import main
    rc = main(["experiment", "--strategy-id", "S1", "--version", "1",
               "--hypothesis", "Momentum works", "--commit"])
    assert rc == 0 and "experiment" in capsys.readouterr().out


def test_cli_backtest(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _strat(eng)
    _ver(eng)
    exp = _exp(eng)
    from jarvis.research_governance.__main__ import main
    rc = main(["backtest", "--experiment-id", exp.experiment_id, "--sharpe", "1.4", "--commit"])
    assert rc == 0 and "backtest" in capsys.readouterr().out


def test_cli_validate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eid = _to_backtested(eng)
    from jarvis.research_governance.__main__ import main
    rc = main(["validate", "--experiment-id", eid, "--oos", "--wf", "--cost-ok",
               "--robust", "--beats-bench", "--commit"])
    assert rc == 0 and "validation" in capsys.readouterr().out


def test_cli_compare(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_experiments(eng)
    from jarvis.research_governance.__main__ import main
    rc = main(["compare", "--experiment-a", a, "--experiment-b", b, "--commit"])
    assert rc == 0 and "comparison" in capsys.readouterr().out


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.__main__ import main
    assert main(["report"]) == 0
    assert "strategy_count" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_governance.__main__ import main
    assert main(["replay"]) == 0
    assert "deterministic" in capsys.readouterr().out


# ── 79~88. 보안/충돌회피/불변 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "portfolio", _j + "broker_readonly", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.research_governance.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.research_governance.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", ".buy(", ".sell(",
                       "kill_switch(", "deploy_strategy", "allocate_capital", "run_live"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_portfolio():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.research_governance.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "portfolio.",
                       "rebalance(", "capital_deploy"):
            assert banned not in src, f"{m} has broker/portfolio verb {banned}"


def test_no_autonomous_deployment():
    import importlib
    import inspect
    for m in ("engine", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.research_governance.{m}"))
        for banned in ("auto_deploy", "auto_approve", "activate_strategy", "promote_to_live"):
            assert banned not in src, f"{m} has autonomous verb {banned}"


def test_ledger_no_delete_api():
    import inspect
    from jarvis.research_governance import ledger as L
    src = inspect.getsource(L)
    for banned in ("def delete", "def update", "def remove", "def overwrite"):
        assert banned not in src


def test_existing_registry_unchanged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 기존 전략 레지스트리(registry.jsonl)를 두고 P10.2 가 절대 건드리지 않음
    with open(sp("registry.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "legacy", "status": "APPROVED"}) + "\n")
    before = hashlib.sha256(open(sp("registry.jsonl"), "rb").read()).hexdigest()
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    after = hashlib.sha256(open(sp("registry.jsonl"), "rb").read()).hexdigest()
    assert before == after
    assert os.path.exists(sp("rg_strategies.jsonl"))


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("research_governance", "strategy_deploy", "auto_approve"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_no_config_mutation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    import jarvis.config as cfg
    from jarvis.permissions.policy import FORBIDDEN
    a0, f0 = cfg.AUTONOMY_LEVEL, len(FORBIDDEN)
    eng = _eng()
    eid = _to_backtested(eng)
    eng.record_validation(eid, _PASS_CHECKS, T0, commit=True)
    assert cfg.AUTONOMY_LEVEL == a0 and len(FORBIDDEN) == f0


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
