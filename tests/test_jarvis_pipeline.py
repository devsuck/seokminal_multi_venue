"""Jarvis 파이프라인 오케스트레이터 테스트 — 체이닝 + BH-FDR 다중검정 예산.

핵심: paper_candidate 승격 = critic 통과 AND BH-FDR 생존. 예산 조이면 승격 막힌다.
"""
from __future__ import annotations

import os

import pytest

from tests.jarvis_state_isolation import isolate_jarvis_state

from jarvis.pipeline import _demo_specs, run_batch
from jarvis.registry import Status, StrategyRegistry


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    isolate_jarvis_state(monkeypatch, tmp_path)
    return tmp_path


def _final(report, sid):
    return next(d["final"] for d in report["decisions"] if d["strategy_id"] == sid)


def test_batch_promotes_real_edge_alpha_10():
    rep = run_batch(_demo_specs(), alpha=0.1, auto_deploy=False)
    assert _final(rep, "cb_bw_overhang_release_v1") == "blocked_by_data"
    # 합성 PEAD = critic+BH 통과하나 레드팀이 실통제(survivorship·cost_stress 등) 미실행으로 BLOCK
    assert "레드팀" in _final(rep, "kr_earnings_surprise_pead_v1")
    assert _final(rep, "cb_bw_issuance_negdrift_v1") == "rejected"
    reg = StrategyRegistry()
    assert reg.state("kr_earnings_surprise_pead_v1")["status"] == Status.WATCHLIST.value


def test_redteam_gate_blocks_synthetic_from_paper():
    # 레드팀 게이트: 합성은 실통제 미실행 → 페이퍼 못 감(정직). 아무것도 배포 안 됨.
    rep = run_batch(_demo_specs(), alpha=0.1, auto_deploy=True)
    assert not any(d.get("deployed") for d in rep["forward_deployments"])
    reg = StrategyRegistry()
    assert reg.state("kr_earnings_surprise_pead_v1")["status"] == Status.WATCHLIST.value


def test_bh_fdr_budget_gates_promotion():
    # alpha를 조이면 PEAD(p≈0.004)도 BH 임계 미달 → paper_candidate 승격 차단
    rep = run_batch(_demo_specs(), alpha=0.01)
    final = _final(rep, "kr_earnings_surprise_pead_v1")
    assert "watchlist" in final and "BH-FDR" in final
    reg = StrategyRegistry()
    st = reg.state("kr_earnings_surprise_pead_v1")["status"]
    assert st == Status.WATCHLIST.value  # paper_candidate 아님


def test_blocked_hypothesis_never_tested():
    rep = run_batch(_demo_specs(), alpha=0.1)
    # 데이터 게이트 차단 = BH 대상(tested)에서 제외
    assert rep["n_hypotheses"] == 7  # SEED_QUEUE 현재 크기
    assert rep["n_tested"] == 3  # synthetic_demo만 테스트, blocked 4개 제외
    reg = StrategyRegistry()
    assert reg.state("cb_bw_overhang_release_v1")["status"] == Status.BLOCKED_BY_DATA.value


def test_bh_survivor_count_reported():
    rep = run_batch(_demo_specs(), alpha=0.1)
    assert rep["bh_fdr"]["n_survivors"] == 1
    assert rep["bh_fdr"]["threshold"] is not None
