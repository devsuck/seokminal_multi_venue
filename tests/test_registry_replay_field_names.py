"""jarvis.agents.backtest.run()과 research.lab.evaluator.evaluate_precomputed()의
replay 경로 — registry row 다수 컨벤션(net/percentile)을 우선 읽는지 회귀 확인.

2026-08-26: 두 곳 다 소수(2건) legacy 필드명(net_pnl/random_pct)만 읽어서 net이
항상 None으로 리플레이되고, critic.review()가 무조건 rejected 처리하던 버그.
"""
from __future__ import annotations

from research.lab.evaluator import evaluate_precomputed
from research.lab.hypotheses import Hypothesis

_ROW = {"hypothesis_id": "auto_fac_kr_size_smb", "net": 0.0423, "percentile": 100.0,
        "p": 0.0033, "wf_first": 0.043, "wf_second": 0.041, "status": "candidate",
        "verdict": "auto-research CANDIDATE"}


def _hyp(precomputed_id="auto_fac_kr_size_smb"):
    return Hypothesis(id=precomputed_id, name=precomputed_id, family="factor", market="KR",
                       thesis="", kill="", entry="", hold="", universe="", cost_bps=0.0,
                       data_mode="real_registry", precomputed_id=precomputed_id)


def test_backtest_run_reads_majority_convention_fields(monkeypatch):
    from jarvis.agents import backtest

    monkeypatch.setattr("research.agents.experiment_registry.already_tested", lambda sid: [_ROW])
    r = backtest.run("auto_fac_kr_size_smb", commit=False)
    assert r["metrics"]["net"] == 0.0423
    assert r["metrics"]["random_percentile"] == 100.0


def test_backtest_run_falls_back_to_legacy_field_names(monkeypatch):
    from jarvis.agents import backtest

    legacy_row = {"net_pnl": 0.05, "random_pct": 90.0, "p": 0.01}
    monkeypatch.setattr("research.agents.experiment_registry.already_tested", lambda sid: [legacy_row])
    r = backtest.run("some_legacy_id", commit=False)
    assert r["metrics"]["net"] == 0.05
    assert r["metrics"]["random_percentile"] == 90.0


def test_evaluate_precomputed_reads_majority_convention_fields(monkeypatch):
    monkeypatch.setattr("research.agents.experiment_registry.already_tested", lambda sid: [_ROW])
    r = evaluate_precomputed(_hyp())
    assert r["backtest"]["strategy_net"] == 0.0423
    assert r["random"]["percentile"] == 100.0
