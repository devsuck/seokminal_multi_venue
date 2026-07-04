"""Lv4 micro-live arm 테스트 — 사람만 arm, 이중게이트, level 4에선 여전히 BLOCK.

핵심: AI는 arm 불가. arm해도 autonomy<6이면 실행 BLOCK. 최소 6개월 페이퍼 강제.
"""
from __future__ import annotations

import os

import pytest

from jarvis.agents import BACKTEST_AGENT, HUMAN_ADMIN
from jarvis.execution.arm import arm, check_micro_live_eligible, disarm, is_armed
from jarvis.execution.gateway import ExecutionGateway
from jarvis.permissions import PermissionDenied
from jarvis.registry import Status, StrategyRegistry


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.execution.arm"):
        import importlib
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


def _to_live_candidate(sid="S"):
    reg = StrategyRegistry()
    reg.register(sid, name=sid, config={"x": 1})
    for s in (Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST,
              Status.PAPER_CANDIDATE, Status.PAPER_ACTIVE):
        reg.transition(sid, s, "t")
    reg.transition(sid, Status.LIVE_CANDIDATE, "approved", approver="human_admin")
    return reg


def test_ai_agent_cannot_arm():
    _to_live_candidate("S1")
    with pytest.raises(PermissionDenied):
        arm("S1", BACKTEST_AGENT, capital_limit=1000, paper_months=12)


def test_human_can_arm_eligible():
    _to_live_candidate("S2")
    r = arm("S2", HUMAN_ADMIN, capital_limit=1000, paper_months=12)
    assert r["armed"] is True
    assert is_armed("S2") is True


def test_arm_requires_min_paper_months():
    _to_live_candidate("S3")
    r = arm("S3", HUMAN_ADMIN, capital_limit=1000, paper_months=2)  # <6
    assert r["armed"] is False
    assert any("insufficient_paper_months" in x for x in r["reasons"])


def test_micro_live_execution_blocked_at_level_4():
    _to_live_candidate("S4")
    arm("S4", HUMAN_ADMIN, capital_limit=1000, paper_months=12)
    res = ExecutionGateway().execute({"proposal_id": "P", "strategy_id": "S4", "orders": []},
                                     risk_result={"risk_status": "APPROVED"}, mode="micro_live")
    # 무장했어도 autonomy 4 < 6 → BLOCKED
    assert res["execution_status"] == "BLOCKED"
    assert "disabled at autonomy level" in res["reason"]


def test_micro_live_rejected_when_not_armed_but_level_ok(monkeypatch):
    # level을 6으로 올려 실행성 게이트 통과시켜도, 무장 안 됐으면 REJECTED
    import jarvis.execution.gateway as gw
    monkeypatch.setattr(gw, "live_execution_enabled", lambda: True)
    _to_live_candidate("S5")  # 무장 안 함
    res = ExecutionGateway().execute({"proposal_id": "P", "strategy_id": "S5", "orders": []},
                                     risk_result={"risk_status": "APPROVED"}, mode="micro_live")
    assert res["execution_status"] == "REJECTED"
    assert "not_armed" in res["reason"]


def test_disarm():
    _to_live_candidate("S6")
    arm("S6", HUMAN_ADMIN, capital_limit=1000, paper_months=12)
    disarm("S6", HUMAN_ADMIN)
    assert is_armed("S6") is False


def test_eligibility_non_live_candidate():
    reg = StrategyRegistry()
    reg.register("S7", name="S7", config={"x": 1})  # draft
    e = check_micro_live_eligible("S7", 12)
    assert e["eligible"] is False
