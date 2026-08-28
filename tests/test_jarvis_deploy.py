"""Lv3 forward 자동배선 테스트 — paper_candidate→paper_active + 러너 배선 + 모니터.

가드: config 미동결/비-paper_candidate는 배포 불가. generic 러너 = 내부원장. live 0.
"""
from __future__ import annotations

import os

import pytest

from tests.jarvis_state_isolation import isolate_jarvis_state

from jarvis.paper.deploy import auto_deploy_all, deploy, deployment_of, run_forward
from jarvis.paper.monitor import monitor
from jarvis.registry import Status, StrategyRegistry


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    isolate_jarvis_state(monkeypatch, tmp_path)
    return tmp_path


def _to_paper_candidate(reg, sid):
    reg.register(sid, name=sid, config={"sid": sid})
    for s in (Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST, Status.PAPER_CANDIDATE):
        reg.transition(sid, s, "test")


def test_deploy_transitions_to_paper_active():
    reg = StrategyRegistry()
    _to_paper_candidate(reg, "S_PC")
    res = deploy("S_PC")
    assert res["deployed"] is True
    assert reg.state("S_PC")["status"] == Status.PAPER_ACTIVE.value
    assert deployment_of("S_PC") is not None


def test_deploy_wires_known_runner():
    reg = StrategyRegistry()
    _to_paper_candidate(reg, "futures_tsmom_32mkt")
    res = deploy("futures_tsmom_32mkt")
    assert res["runner"] == "research.paper.tsmom_forward:generate"
    assert res["rules"]["cadence"] == "monthly"


def test_deploy_generic_runner_for_unknown():
    reg = StrategyRegistry()
    _to_paper_candidate(reg, "SOME_NEW_STRAT")
    res = deploy("SOME_NEW_STRAT")
    assert res["runner"] == "generic"


def test_deploy_blocks_non_paper_candidate():
    reg = StrategyRegistry()
    reg.register("S_DR", name="S_DR", config={"x": 1})  # draft, not frozen
    res = deploy("S_DR")
    assert res["deployed"] is False
    assert "not_paper_candidate" in res["reason"]


def test_deploy_idempotent():
    reg = StrategyRegistry()
    _to_paper_candidate(reg, "S_ID")
    deploy("S_ID")
    again = deploy("S_ID")
    assert again["deployed"] is False
    assert again["reason"] == "already_paper_active"


def test_auto_deploy_all():
    reg = StrategyRegistry()
    _to_paper_candidate(reg, "A1")
    _to_paper_candidate(reg, "A2")
    res = auto_deploy_all()
    assert res["candidates"] == 2
    assert res["deployed"] == 2


def test_monitor_runs_generic_forward():
    reg = StrategyRegistry()
    _to_paper_candidate(reg, "S_MON")
    deploy("S_MON")
    rep = monitor("S_MON")
    assert rep["status"] == Status.PAPER_ACTIVE.value
    assert rep["deployed"] is True
    assert rep["forward"]["available"] is True   # generic 내부원장
    assert rep["live_orders"] == "disabled"


def test_run_forward_missing_data_graceful():
    reg = StrategyRegistry()
    _to_paper_candidate(reg, "futures_tsmom_32mkt")
    deploy("futures_tsmom_32mkt")
    r = run_forward("futures_tsmom_32mkt")
    # 실데이터/TWS 없으면 available False로 우아하게(크래시 없음)
    assert "available" in r
