"""ensemble.py — 복수 전략 합의. base(armed+arm_criteria GO) 없으면 tier_b가
아무리 모여도 무조건 action=none. base 있고 tier_b 2개 이상 동일방향 동의시만 부스트."""
from __future__ import annotations

import os

import pytest

from jarvis.agents import HUMAN_ADMIN
from jarvis.execution import arm as arm_mod
from jarvis.execution import ensemble
from jarvis.registry import Status, StrategyRegistry


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.execution.arm"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


def _armed_strategy(sid="E1"):
    reg = StrategyRegistry()
    reg.register(sid, name=sid, config={})
    for s in (Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST,
              Status.PAPER_CANDIDATE, Status.PAPER_ACTIVE):
        reg.transition(sid, s, "t")
    reg.transition(sid, Status.LIVE_CANDIDATE, "approved", approver="human_admin")
    arm_mod.arm(sid, HUMAN_ADMIN, capital_limit=1000, paper_months=12)
    return reg


_GOOD_EDGE = {"status": "ok", "oos_months": 6, "oos_in_envelope": 5}  # ratio 5/6 >= 2/3


def test_base_signal_none_when_not_armed():
    StrategyRegistry().register("E0", name="E0", config={})
    assert ensemble.base_signal("E0", _GOOD_EDGE, 12, "long") is None


def test_base_signal_none_when_arm_criteria_not_go():
    _armed_strategy("E2")
    bad_edge = {"status": "ok", "oos_months": 1, "oos_in_envelope": 0}
    assert ensemble.base_signal("E2", bad_edge, 1, "long") is None


def test_base_signal_present_when_armed_and_go():
    _armed_strategy("E3")
    sig = ensemble.base_signal("E3", _GOOD_EDGE, 12, "long")
    assert sig is not None
    assert sig["direction"] == "long"


def test_tier_b_signal_requires_draft_and_data_version():
    reg = StrategyRegistry()
    reg.register("T1", name="T1", config={}, data_version="v1")
    assert ensemble.tier_b_signal("T1", "long") is not None
    reg.register("T2", name="T2", config={})  # data_version defaults "unknown"
    assert ensemble.tier_b_signal("T2", "long") is None


def test_evaluate_none_without_base():
    r = ensemble.evaluate(None, [{"strategy_id": "T1", "direction": "long"}])
    assert r["action"] == "none"


def test_evaluate_no_boost_below_threshold():
    base = {"strategy_id": "E3", "direction": "long"}
    r = ensemble.evaluate(base, [{"strategy_id": "T1", "direction": "long"}])
    assert r["action"] == "trade"
    assert r["size_multiplier"] == 1.0


def test_evaluate_boosts_when_two_tier_b_agree():
    base = {"strategy_id": "E3", "direction": "long"}
    tier_b = [
        {"strategy_id": "T1", "direction": "long"},
        {"strategy_id": "T2", "direction": "long"},
        {"strategy_id": "T3", "direction": "short"},  # 반대방향, 카운트 안 됨
    ]
    r = ensemble.evaluate(base, tier_b)
    assert r["size_multiplier"] == ensemble.BOOST_MULTIPLIER
    assert set(r["agreeing_tier_b"]) == {"T1", "T2"}


def test_tier_b_alone_never_triggers():
    # base 없이 tier_b 여러개 동의해도 action은 none — 단일전략(사실상 tier_b뿐)
    # 트리거 절대 금지 요구사항의 핵심 회귀 테스트.
    tier_b = [{"strategy_id": f"T{i}", "direction": "long"} for i in range(5)]
    r = ensemble.evaluate(None, tier_b)
    assert r["action"] == "none"
