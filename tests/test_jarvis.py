"""Jarvis Quant OS 안전 테스트 — 권한·FSM·리스크·집행·감사 불변식.

핵심: AI는 자기 집행권한 확장 불가, 불법전이 거부, live 차단, 감사 append-only.
"""
from __future__ import annotations

import os

import pytest

from tests.jarvis_state_isolation import isolate_jarvis_state

import jarvis
from jarvis.agents import BACKTEST_AGENT, HUMAN_ADMIN, RESEARCH_AGENT
from jarvis.agents import datagate
from jarvis.execution.gateway import ExecutionGateway
from jarvis.permissions import PermissionDenied, check, require
from jarvis.registry.lifecycle import IllegalTransition, Status, StrategyRegistry, config_hash
from jarvis.risk import RiskGovernor, RiskLimits


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """모든 상태파일을 tmp로 격리(실 _state 오염 방지)."""
    isolate_jarvis_state(monkeypatch, tmp_path)
    return tmp_path


def _build(reg: StrategyRegistry, sid: str, target: Status, approver=None) -> None:
    """전략을 target 상태까지 합법 경로로 진행."""
    reg.register(sid, name=sid, config={"sid": sid})
    path = {
        Status.DATA_AUDIT_PASSED: [Status.DATA_AUDIT_PASSED],
        Status.BACKTESTED: [Status.DATA_AUDIT_PASSED, Status.BACKTESTED],
        Status.WATCHLIST: [Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST],
        Status.REJECTED: [Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.REJECTED],
        Status.PAPER_CANDIDATE: [Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST, Status.PAPER_CANDIDATE],
        Status.PAPER_ACTIVE: [Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST, Status.PAPER_CANDIDATE, Status.PAPER_ACTIVE],
        Status.LIVE_CANDIDATE: [Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST, Status.PAPER_CANDIDATE, Status.PAPER_ACTIVE, Status.LIVE_CANDIDATE],
    }[target]
    for step in path:
        reg.transition(sid, step, "test", approver=approver if step in
                       (Status.LIVE_CANDIDATE, Status.MICRO_LIVE, Status.CONSTRAINED_LIVE) else None)


# ── 권한 ─────────────────────────────────────────────────────
def test_live_execution_permission_denied():
    assert check(RESEARCH_AGENT, "execute_micro_live_order") is False


def test_ai_cannot_modify_risk_limits():
    assert check(BACKTEST_AGENT, "modify_risk_limit") is False
    with pytest.raises(PermissionDenied):
        require(RESEARCH_AGENT, "modify_risk_limit")


def test_ai_cannot_modify_frozen_config():
    assert check(BACKTEST_AGENT, "modify_frozen_config") is False


def test_nobody_can_delete_audit_log():
    # 사람 admin이어도 FORBIDDEN
    assert check(HUMAN_ADMIN, "delete_audit_log") is False


def test_human_admin_can_modify_risk_limit():
    assert check(HUMAN_ADMIN, "modify_risk_limit") is True


# ── 레지스트리 FSM ───────────────────────────────────────────
def test_rejected_cannot_be_promoted_to_paper():
    reg = StrategyRegistry()
    _build(reg, "S_REJ", Status.REJECTED)
    with pytest.raises(IllegalTransition):
        reg.transition("S_REJ", Status.PAPER_CANDIDATE, "revive attempt")


def test_sanity_only_cannot_become_paper_candidate():
    reg = StrategyRegistry()
    reg.register("S_SAN", name="S_SAN", config={"x": 1})
    reg.transition("S_SAN", Status.SANITY_CHECK_ONLY, "data gate sanity")
    reg.transition("S_SAN", Status.BACKTESTED, "sanity backtest")
    reg.transition("S_SAN", Status.WATCHLIST, "watch")
    with pytest.raises(IllegalTransition):
        reg.transition("S_SAN", Status.PAPER_CANDIDATE, "should block")


def test_illegal_transition_draft_to_live():
    reg = StrategyRegistry()
    reg.register("S_D", name="S_D", config={"x": 1})
    with pytest.raises(IllegalTransition):
        reg.transition("S_D", Status.CONSTRAINED_LIVE, "jump")


def test_live_transition_requires_human_approver():
    reg = StrategyRegistry()
    _build(reg, "S_PA", Status.PAPER_ACTIVE)
    with pytest.raises(IllegalTransition):
        reg.transition("S_PA", Status.LIVE_CANDIDATE, "no approver")  # approver 없음
    reg.transition("S_PA", Status.LIVE_CANDIDATE, "approved", approver="human_admin")
    assert reg.state("S_PA")["status"] == Status.LIVE_CANDIDATE.value


def test_config_frozen_at_paper_candidate():
    reg = StrategyRegistry()
    _build(reg, "S_PC", Status.PAPER_CANDIDATE)
    assert reg.state("S_PC")["frozen"] is True


# ── 데이터 게이트 ────────────────────────────────────────────
def test_data_gate_blocks_missing_pit():
    r = datagate.check("KR_CB_RELEASE", ["daily_ohlcv", "cb_bw_release_linkage",
                                         "remaining_convertible_balance"], commit=False)
    assert r["status"] == "BLOCKED_BY_DATA"
    assert "cb_bw_release_linkage" in r["blocked_features"]


def test_data_gate_pass_basic():
    r = datagate.check("KR_BASIC", ["daily_ohlcv", "market_cap", "delisting_history"], commit=False)
    assert r["status"] == "DATA_GATE_PASS"


# ── 리스크 거버너 ────────────────────────────────────────────
def test_risk_governor_blocks_unapproved_strategy():
    reg = StrategyRegistry()
    _build(reg, "S_PCX", Status.PAPER_CANDIDATE)
    res = RiskGovernor().check({"proposal_id": "P1", "strategy_id": "S_PCX",
                                "orders": [{"symbol": "ES", "quantity": 1, "price": 100}]}, RiskLimits())
    assert res["risk_status"] == "REJECTED"
    assert "not_live_candidate" in res["reason"]


def test_risk_governor_config_hash_mismatch():
    reg = StrategyRegistry()
    _build(reg, "S_LC", Status.LIVE_CANDIDATE, approver="human_admin")
    res = RiskGovernor().check(
        {"proposal_id": "P2", "strategy_id": "S_LC", "orders": [{"symbol": "ES", "quantity": 1, "price": 100}]},
        RiskLimits(approved_universe={"ES"}), expected_config_hash="sha256:WRONG")
    assert res["risk_status"] == "REJECTED"
    assert "config_hash_mismatch" in res["reason"]


# ── 집행 게이트웨이 ──────────────────────────────────────────
def test_execution_gateway_blocks_live():
    res = ExecutionGateway().execute({"proposal_id": "P3", "strategy_id": "X", "orders": []}, mode="live")
    assert res["execution_status"] == "BLOCKED"
    assert "disabled" in res["reason"]


def test_execution_requires_risk_approval():
    res = ExecutionGateway().execute({"proposal_id": "P4", "strategy_id": "X"},
                                     risk_result={"risk_status": "REJECTED"}, mode="paper")
    assert res["execution_status"] == "REJECTED"


# ── 페이퍼 원장 ──────────────────────────────────────────────
def test_paper_ledger_only_for_paper_status():
    from jarvis.paper.ledger import PaperLedger
    reg = StrategyRegistry()
    _build(reg, "S_PAP", Status.PAPER_ACTIVE)
    led = PaperLedger()
    led.create_entry("S_PAP", "005930", "BUY", 10, 70000)
    assert led.summary("S_PAP")["entries"] == 1

    _build(reg, "S_DRAFT", Status.DATA_AUDIT_PASSED)
    with pytest.raises(PermissionError):
        led.create_entry("S_DRAFT", "005930", "BUY", 10, 70000)


# ── 감사 append-only ─────────────────────────────────────────
def test_audit_is_append_only():
    import jarvis.audit as audit
    assert not hasattr(audit, "delete")
    assert not hasattr(audit, "clear")
    before = len(audit.read_all())
    check(RESEARCH_AGENT, "run_backtest")  # 감사 1건 발생
    assert len(audit.read_all()) == before + 1


# ── 부트/상태 ────────────────────────────────────────────────
def test_boot_and_status_live_disabled():
    jarvis.boot()
    s = jarvis.status()
    assert s["live_execution"] == "disabled"
    assert s["autonomy_level"] <= 5
    assert "AI can now trade live" not in jarvis.banner()
