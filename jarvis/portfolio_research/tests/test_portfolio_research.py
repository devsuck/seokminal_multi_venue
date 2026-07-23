"""P10.4 Portfolio Research Intelligence 테스트. **연구·기록 전용.**

포트폴리오 레지스트리(불변)·버전·생명주기(DRAFT→...→ARCHIVED, 차단전이)·가설·구성연구(이론적
가중치)·백테스트·리스크분석(PASS/WARNING/FAILED)·비교(자동선택 없음)·계보·verify(체인/변조/중복)·
replay·CLI·보안(금지import·집행/브로커/자본배분 없음·기존 원장 무변경·삭제 API 없음·불변·
VALIDATED≠deployment·append-only).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.portfolio_research import ledger
from jarvis.portfolio_research import models as M
from jarvis.portfolio_research.engine import PortfolioResearchEngine
from jarvis.portfolio_research.models import (
    ARCHIVED,
    BACKTESTED,
    CONSTRUCTED,
    DRAFT,
    FAILED,
    PASS,
    RISK_ANALYZED,
    VALIDATED,
    WARNING,
    IllegalTransition,
    ImmutablePortfolioError,
    ImmutableVersionError,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"

_WEIGHTS = {"ALPHA_MOM": 0.4, "ALPHA_VAL": 0.35, "ALPHA_QUAL": 0.25}
_PASS_RISK = {"max_weight": 0.2, "n_holdings": 5, "concentration": 0.25, "var_95": 0.05}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.portfolio_research.ledger.state_path", sp)
    return sp


def _eng():
    return PortfolioResearchEngine()


def _pf(eng, pid="PF1", commit=True):
    return eng.register_portfolio(pid, f"{pid} name", "desc", "quant", "max_sharpe", T0,
                                  commit=commit)


def _ver(eng, pid="PF1", ver="1", method="signal_weighted", universe=None, commit=True):
    return eng.create_version(pid, ver, "quant", method,
                              universe or ["ALPHA_MOM", "ALPHA_VAL", "ALPHA_QUAL"],
                              {"max_weight": 0.5}, "dg:D@1", T0, commit=commit)


def _to_study(eng, pid="PF1", ver="1"):
    _pf(eng, pid)
    _ver(eng, pid, ver)
    return eng.record_construction(pid, ver, "signal_weighted", dict(_WEIGHTS), "monthly", T0,
                                   commit=True)


def _to_backtested(eng, pid="PF1", ver="1"):
    st = _to_study(eng, pid, ver)
    eng.record_backtest(st.study_id, total_return=0.35, volatility=0.14, sharpe=1.7,
                        max_drawdown=-0.09, turnover=1.8, diversification=0.7, now=T0,
                        commit=True)
    return st.study_id


def _to_risk_analyzed(eng, pid="PF1", ver="1"):
    sid = _to_backtested(eng, pid, ver)
    eng.record_risk_analysis(sid, dict(_PASS_RISK), T0, commit=True)
    return sid


# ── 1~16. models 순수 ──
def test_can_transition_allowed():
    assert M.can_transition("", DRAFT) and M.can_transition(DRAFT, CONSTRUCTED)
    assert M.can_transition(CONSTRUCTED, BACKTESTED) and M.can_transition(BACKTESTED, RISK_ANALYZED)
    assert M.can_transition(RISK_ANALYZED, VALIDATED) and M.can_transition(VALIDATED, ARCHIVED)


def test_can_transition_blocked():
    assert not M.can_transition(DRAFT, BACKTESTED)
    assert not M.can_transition(CONSTRUCTED, VALIDATED)
    assert not M.can_transition(ARCHIVED, DRAFT)


def test_portfolio_hash_deterministic():
    assert M.portfolio_hash("P", "n", "a", "o", "d") == M.portfolio_hash("P", "n", "a", "o", "d")


def test_version_hash_deterministic():
    assert M.version_hash("P", "1", "m", ["s"], {}, "d") == M.version_hash("P", "1", "m", ["s"], {}, "d")


def test_content_hash_excludes():
    a = {"x": 1, "previous_hash": "p1", "record_hash": "r1"}
    b = {"x": 1, "previous_hash": "p2", "record_hash": "r2"}
    assert M.content_hash(a) == M.content_hash(b)


def test_version_key():
    assert M.version_key("P1", "2") == "P1@2"


def test_normalize_weights():
    assert M.normalize_weights({"A": 2, "B": 2}) == {"A": 0.5, "B": 0.5}


def test_normalize_weights_zero():
    assert M.normalize_weights({}) == {}


def test_concentration_hhi():
    assert M.concentration_hhi({"A": 0.5, "B": 0.5}) == 0.5
    assert M.concentration_hhi({"A": 1.0}) == 1.0


def test_risk_verdict_pass():
    assert M.risk_verdict(_PASS_RISK) == PASS


def test_risk_verdict_failed_concentration():
    assert M.risk_verdict(dict(_PASS_RISK, max_weight=0.6)) == FAILED


def test_risk_verdict_failed_holdings():
    assert M.risk_verdict(dict(_PASS_RISK, n_holdings=1)) == FAILED


def test_risk_verdict_warning():
    assert M.risk_verdict(dict(_PASS_RISK, max_weight=0.35)) == WARNING
    assert M.risk_verdict(dict(_PASS_RISK, var_95=0.15)) == WARNING


def test_comparison_recommendation():
    assert M.comparison_recommendation(1.5, 1.0) == M.A_PREFERRED
    assert M.comparison_recommendation(1.0, 1.5) == M.B_PREFERRED
    assert M.comparison_recommendation(1.0, 1.05) == M.INCONCLUSIVE


def test_detect_cycle():
    assert M.detect_cycle([("A", "B"), ("B", "A")])
    assert M.detect_cycle([("A", "B")]) == []


def test_artifact_id_deterministic():
    assert M.artifact_id("PORTFOLIO", "P1") == M.artifact_id("PORTFOLIO", "P1")


# ── 17~21. Portfolio Registry ──
def test_register_portfolio_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _pf(_eng(), commit=False)
    assert p.portfolio_id == "PF1" and p.portfolio_hash.startswith("sha256:")


def test_register_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _pf(_eng())
    assert len(ledger.read_portfolios()) == 1


def test_register_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _pf(eng)
    assert len(ledger.read_portfolios()) == 1


def test_register_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng, pid="PF1")
    with pytest.raises(ImmutablePortfolioError):
        eng.register_portfolio("PF1", "DIFFERENT", "d", "quant", "max_sharpe", T0, commit=True)


def test_register_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _pf(_eng())
    assert any(a["artifact_type"] == "PORTFOLIO" for a in ledger.read_artifacts())


# ── 22~26. Version ──
def test_create_version_draft(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    v = _ver(eng)
    assert v.to_state == DRAFT and eng.current_state("PF1@1") == DRAFT


def test_version_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    assert len(ledger.read_versions()) == 1


def test_version_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    _ver(eng)
    assert len(ledger.version_events_for("PF1@1")) == 1


def test_version_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng, method="equal_weight")
    with pytest.raises(ImmutableVersionError):
        _ver(eng, method="risk_parity")


def test_current_state_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_state("GHOST@1") == ""


# ── 27~31. Hypothesis ──
def test_create_hypothesis_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    h = eng.create_hypothesis("PF1", "1", "Diversification improves Sharpe", "prior", T0,
                              commit=True)
    assert h.hypothesis_id.startswith("PHY:") and len(ledger.read_hypotheses()) == 1


def test_hypothesis_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    eng.create_hypothesis("PF1", "1", "H", "", T0, commit=True)
    arts = {a["artifact_type"]: a for a in ledger.read_artifacts()}
    assert arts["HYPOTHESIS"]["parent_artifact"] == M.artifact_id("PORTFOLIO", "PF1")


def test_hypothesis_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    eng.create_hypothesis("PF1", "1", "H", "", T0, commit=True)
    assert len(ledger.read_hypotheses()) == 1


def test_hypothesis_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    eng.create_hypothesis("PF1", "1", "H", "", T0, commit=True)
    eng.create_hypothesis("PF1", "1", "H", "", T1, commit=True)
    assert len(ledger.read_hypotheses()) == 1


def test_hypothesis_no_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    eng.create_hypothesis("PF1", "1", "H", "", T0, commit=True)
    assert eng.current_state("PF1@1") == DRAFT   # 가설은 상태 전이 아님


# ── 32~38. Construction (이론적 가중치) ──
def test_construction_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    st = _to_study(eng)
    assert st.study_id.startswith("PCS:") and len(ledger.read_studies()) == 1


def test_construction_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_study(eng)
    assert eng.current_state("PF1@1") == CONSTRUCTED


def test_construction_normalizes_weights(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    st = eng.record_construction("PF1", "1", "equal_weight", {"A": 1, "B": 1}, "monthly", T0,
                                 commit=True)
    assert st.weights == {"A": 0.5, "B": 0.5}


def test_construction_concentration(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    st = eng.record_construction("PF1", "1", "equal_weight", {"A": 1, "B": 1}, "monthly", T0)
    assert st.concentration == 0.5


def test_construction_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_study(eng)
    assert any(a["artifact_type"] == "CONSTRUCTION" for a in ledger.read_artifacts())


def test_construction_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_study(eng)
    assert len(ledger.read_studies()) == 1


def test_construction_is_not_capital_allocation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_study(eng)
    # 구성연구는 이론적 가중치 — 실제 자본배분/포트폴리오 원장 미생성
    for banned in ("portfolio_snapshots.jsonl", "paper_positions.jsonl",
                   "live_execution_requests.jsonl"):
        assert not os.path.exists(sp(banned))


# ── 39~44. Backtest ──
def test_backtest_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    st = _to_study(eng)
    b = eng.record_backtest(st.study_id, sharpe=1.7, now=T0, commit=True)
    assert b.sharpe == 1.7 and len(ledger.read_backtests()) == 1


def test_backtest_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_backtested(eng)
    assert eng.current_state("PF1@1") == BACKTESTED


def test_backtest_metrics(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    st = _to_study(eng)
    b = eng.record_backtest(st.study_id, total_return=0.3, volatility=0.14, sharpe=1.7,
                            max_drawdown=-0.09, turnover=1.8, diversification=0.7, now=T0,
                            commit=True).to_dict()
    for k in ("total_return", "volatility", "sharpe", "max_drawdown", "turnover",
              "diversification"):
        assert k in b


def test_backtest_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    sid = _to_backtested(eng)
    arts = {a["artifact_type"]: a for a in ledger.read_artifacts()}
    assert arts["BACKTEST"]["parent_artifact"] == M.artifact_id("CONSTRUCTION", sid)


def test_backtest_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_backtested(eng)
    assert len(ledger.read_backtests()) == 1


def test_backtest_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    st = _to_study(eng)
    eng.record_backtest(st.study_id, sharpe=1.7, now=T0, commit=True)
    eng.record_backtest(st.study_id, sharpe=1.7, now=T1, commit=True)
    assert len(ledger.read_backtests()) == 1


# ── 45~50. Risk Analysis ──
def test_risk_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    sid = _to_backtested(eng)
    r = eng.record_risk_analysis(sid, dict(_PASS_RISK), T0, commit=True)
    assert r.risk_verdict == PASS


def test_risk_failed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    sid = _to_backtested(eng)
    r = eng.record_risk_analysis(sid, dict(_PASS_RISK, max_weight=0.6), T0, commit=True)
    assert r.risk_verdict == FAILED


def test_risk_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_risk_analyzed(eng)
    assert eng.current_state("PF1@1") == RISK_ANALYZED


def test_risk_metrics_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    sid = _to_backtested(eng)
    r = eng.record_risk_analysis(sid, dict(_PASS_RISK), T0, commit=True).to_dict()
    assert "metrics" in r and r["metrics"]["max_weight"] == 0.2


def test_risk_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_risk_analyzed(eng)
    assert any(a["artifact_type"] == "RISK_ANALYSIS" for a in ledger.read_artifacts())


def test_risk_append_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    sid = _to_backtested(eng)
    eng.record_risk_analysis(sid, dict(_PASS_RISK), T0, commit=True)
    eng.record_risk_analysis(sid, dict(_PASS_RISK), T1, commit=True)
    assert len(ledger.read_risk()) == 1


# ── 51~56. Lifecycle ──
def test_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_risk_analyzed(eng)
    eng.validate_portfolio("PF1", "1", T0, commit=True)
    eng.archive_portfolio("PF1", "1", T0, commit=True)
    assert eng.current_state("PF1@1") == ARCHIVED


def test_validate_requires_risk_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_backtested(eng)   # BACKTESTED, not RISK_ANALYZED
    with pytest.raises(IllegalTransition):
        eng.validate_portfolio("PF1", "1", T0, commit=True)


def test_archive_requires_validated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_risk_analyzed(eng)
    with pytest.raises(IllegalTransition):
        eng.archive_portfolio("PF1", "1", T0, commit=True)


def test_illegal_skip_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    with pytest.raises(IllegalTransition):
        eng.transition("PF1", "1", BACKTESTED, T0, commit=True)   # DRAFT→BACKTESTED 차단


def test_illegal_from_archived(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_risk_analyzed(eng)
    eng.validate_portfolio("PF1", "1", T0, commit=True)
    eng.archive_portfolio("PF1", "1", T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition("PF1", "1", VALIDATED, T0, commit=True)


def test_validated_not_deployment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.permissions.policy import FORBIDDEN
    f0 = len(FORBIDDEN)
    eng = _eng()
    _to_risk_analyzed(eng)
    eng.validate_portfolio("PF1", "1", T0, commit=True)
    assert eng.current_state("PF1@1") == VALIDATED
    assert len(FORBIDDEN) == f0   # VALIDATED 는 실제 배포/권한 변경 아님


# ── 57~61. Comparison ──
def _two_portfolios(eng):
    _pf(eng, pid="PF1")
    _ver(eng, pid="PF1")
    st1 = eng.record_construction("PF1", "1", "signal_weighted", dict(_WEIGHTS), "monthly", T0,
                                  commit=True)
    eng.record_backtest(st1.study_id, sharpe=1.8, now=T0, commit=True)
    _pf(eng, pid="PF2")
    _ver(eng, pid="PF2")
    st2 = eng.record_construction("PF2", "1", "equal_weight", {"A": 1, "B": 1}, "monthly", T0,
                                  commit=True)
    eng.record_backtest(st2.study_id, sharpe=1.1, now=T0, commit=True)


def test_compare_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_portfolios(eng)
    c = eng.compare_portfolios("PF1", "PF2", T0, commit=True)
    assert len(ledger.read_comparisons()) == 1 and c.comparison_id.startswith("PCM:")


def test_compare_deltas(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_portfolios(eng)
    c = eng.compare_portfolios("PF1", "PF2", T0)
    assert round(c.deltas["sharpe"], 2) == 0.7


def test_compare_recommendation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_portfolios(eng)
    c = eng.compare_portfolios("PF1", "PF2", T0)
    assert c.recommendation == M.A_PREFERRED


def test_compare_no_auto_select(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_portfolios(eng)
    eng.compare_portfolios("PF1", "PF2", T0, commit=True)
    assert eng.current_state("PF1@1") == BACKTESTED   # 상태 변경 없음


def test_compare_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_portfolios(eng)
    eng.compare_portfolios("PF1", "PF2", T0, commit=True)
    eng.compare_portfolios("PF1", "PF2", T1, commit=True)
    assert len(ledger.read_comparisons()) == 1


# ── 62~65. Report ──
def test_report_portfolio_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng, pid="A")
    _pf(eng, pid="B")
    assert eng.generate_portfolio_report(T0).portfolio_count == 2


def test_report_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_risk_analyzed(eng)
    assert eng.generate_portfolio_report(T0).state_distribution.get(RISK_ANALYZED) == 1


def test_report_risk_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_risk_analyzed(eng)
    assert eng.generate_portfolio_report(T0).risk_pass == 1


def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_risk_analyzed(eng)
    rep = eng.generate_portfolio_report(T0)
    assert rep.construction_count == 1 and rep.backtest_count == 1 and rep.risk_analysis_count == 1


# ── 66~73. Verify / tamper / replay / lineage ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.verify import verify_chain
    eng = _eng()
    _to_risk_analyzed(eng)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 5


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.verify import verify_chain
    _pf(_eng())
    path = sp("pr_portfolios.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["objective"] = "TAMPERED"
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    assert verify_chain()["ledgers"]["pr_portfolios.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.verify import verify_chain
    eng = _eng()
    _pf(eng, pid="A")
    _pf(eng, pid="B")
    path = sp("pr_portfolios.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ledgers"]["pr_portfolios.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.verify import verify_chain
    _pf(_eng())
    path = sp("pr_portfolios.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    assert verify_chain()["ledgers"]["pr_portfolios.jsonl"]["reason"] in {"duplicate_id",
                                                                          "previous_hash_broken"}


def test_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.verify import lineage_validation
    eng = _eng()
    _to_risk_analyzed(eng)
    assert lineage_validation()["ok"] is True


def test_lineage_circular_dependency(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.verify import lineage_validation
    with open(sp("pr_artifacts.jsonl"), "w") as f:
        f.write(json.dumps({"artifact_id": "A", "parent_artifact": "B"}) + "\n")
        f.write(json.dumps({"artifact_id": "B", "parent_artifact": "A"}) + "\n")
    res = lineage_validation()
    assert res["ok"] is False and any("circular_dependency" in i for i in res["issues"])


def test_lineage_dangling_backtest(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.verify import lineage_validation
    with open(sp("pr_backtests.jsonl"), "w") as f:
        f.write(json.dumps({"backtest_id": "B1", "study_id": "ghost_study"}) + "\n")
    res = lineage_validation()
    assert any("dangling_backtest" in i for i in res["issues"])


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _to_risk_analyzed(eng)
    from jarvis.portfolio_research.verify import replay
    assert replay(eng, T0)["deterministic"] is True


# ── 74~82. CLI ──
def test_cli_portfolio(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.__main__ import main
    rc = main(["portfolio", "--portfolio-id", "P1", "--name", "n", "--author", "a",
               "--objective", "max_sharpe", "--version", "1", "--commit"])
    assert rc == 0 and "portfolio" in capsys.readouterr().out


def test_cli_hypothesis(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    from jarvis.portfolio_research.__main__ import main
    rc = main(["hypothesis", "--portfolio-id", "PF1", "--version", "1", "--statement", "H",
               "--commit"])
    assert rc == 0 and "hypothesis" in capsys.readouterr().out


def test_cli_construct(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng)
    _ver(eng)
    from jarvis.portfolio_research.__main__ import main
    rc = main(["construct", "--portfolio-id", "PF1", "--version", "1", "--method",
               "equal_weight", "--weights-json", '{"A":1,"B":1}', "--commit"])
    assert rc == 0 and "construction" in capsys.readouterr().out


def test_cli_backtest(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    st = _to_study(eng)
    from jarvis.portfolio_research.__main__ import main
    rc = main(["backtest", "--study-id", st.study_id, "--sharpe", "1.7", "--commit"])
    assert rc == 0 and "backtest" in capsys.readouterr().out


def test_cli_risk(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    sid = _to_backtested(eng)
    from jarvis.portfolio_research.__main__ import main
    rc = main(["risk", "--study-id", sid, "--max-weight", "0.2", "--n-holdings", "5",
               "--concentration", "0.25", "--var95", "0.05", "--commit"])
    assert rc == 0 and "risk_analysis" in capsys.readouterr().out


def test_cli_compare(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_portfolios(eng)
    from jarvis.portfolio_research.__main__ import main
    rc = main(["compare", "--portfolio-a", "PF1", "--portfolio-b", "PF2", "--commit"])
    assert rc == 0 and "comparison" in capsys.readouterr().out


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.__main__ import main
    assert main(["report"]) == 0
    assert "portfolio_count" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.portfolio_research.__main__ import main
    assert main(["replay"]) == 0
    assert "deterministic" in capsys.readouterr().out


# ── 83~91. 보안/불변 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "portfolio.", _j + "broker_readonly", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.portfolio_research.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.portfolio_research.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", ".buy(", ".sell(",
                       "kill_switch(", "execute_allocation", "run_live", "deploy_portfolio"):
            assert banned not in src, f"{m} has execution verb {banned}"


def test_no_broker_or_capital_allocation():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.portfolio_research.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "allocate_capital",
                       "rebalance_live", "auto_deploy"):
            assert banned not in src, f"{m} has broker/capital verb {banned}"


def test_ledger_no_delete_api():
    import inspect
    from jarvis.portfolio_research import ledger as L
    src = inspect.getsource(L)
    for banned in ("def delete", "def update", "def remove", "def overwrite"):
        assert banned not in src


def test_existing_ledger_unchanged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 기존 계층 원장(P10.3 ai_signals, portfolio 상태)을 두고 P10.4 무변경
    for fn in ("ai_signals.jsonl", "portfolio_snapshots.jsonl"):
        with open(sp(fn), "w") as f:
            f.write(json.dumps({"pre": "existing"}) + "\n")
    before = {fn: hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
              for fn in ("ai_signals.jsonl", "portfolio_snapshots.jsonl")}
    eng = _eng()
    _to_risk_analyzed(eng)
    after = {fn: hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
             for fn in ("ai_signals.jsonl", "portfolio_snapshots.jsonl")}
    assert before == after
    assert os.path.exists(sp("pr_portfolios.jsonl"))


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("portfolio_research", "portfolio_deploy", "allocate_live"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_no_config_mutation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    import jarvis.config as cfg
    from jarvis.permissions.policy import FORBIDDEN
    a0, f0 = cfg.AUTONOMY_LEVEL, len(FORBIDDEN)
    eng = _eng()
    _to_risk_analyzed(eng)
    assert cfg.AUTONOMY_LEVEL == a0 and len(FORBIDDEN) == f0


def test_append_only_never_deletes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _pf(eng, pid="A")
    n1 = len(ledger.read_portfolios())
    _pf(eng, pid="B")
    assert len(ledger.read_portfolios()) > n1


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
