"""live_router.route_all — armed+GO 기여자 없으면 절대 트리거 안 함(Tier B 단독금지
회귀, ensemble.py의 test_tier_b_alone_never_triggers 후신). armed+GO 있으면 route,
2개 이상 동일방향 동의시 부스트, broker_bridge 예외는 blocked에 기록하고 계속 진행."""
from __future__ import annotations

import os

import pytest

from jarvis.agents import HUMAN_ADMIN
from jarvis.execution import arm as arm_mod
from jarvis.execution import live_router
from jarvis.fusion import providers as fusion_providers
from jarvis.fusion.types import StrategyPerf, StrategySignal
from jarvis.registry import Status, StrategyRegistry

SID = "kr_dart_buyback_drift_v1"
SID2 = "kr_turn_of_month_v1_PORTFOLIO"


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.execution.arm"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    # 실전 adapter 자기등록(register_all())을 여기서 1회 선점 — collect_signals()가
    # 테스트 본문 안에서 처음 import하면 PROVIDER_REGISTRY의 테스트 mock(SID/SID2는
    # 실제 adapter도 등록된 strategy_id라 겹침)을 실전 adapter로 덮어써버림.
    fusion_providers._ensure_adapters()
    fusion_providers.PROVIDER_REGISTRY.clear()
    yield tmp_path
    fusion_providers.PROVIDER_REGISTRY.clear()


def _register_paper_active(sid):
    """armed(LIVE_CANDIDATE/MICRO_LIVE만 arm 가능)과 fusion-eligible(paper_active/
    micro_live/constrained_live/live만) 상태 집합의 교집합은 MICRO_LIVE뿐 —
    거기까지 승격해야 arm()도 성공하고 collect_signals()에도 잡힌다."""
    reg = StrategyRegistry()
    reg.register(sid, name=sid, config={})
    for s in (Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST,
              Status.PAPER_CANDIDATE, Status.PAPER_ACTIVE):
        reg.transition(sid, s, "t")
    reg.transition(sid, Status.LIVE_CANDIDATE, "approved", approver="human_admin")
    reg.transition(sid, Status.MICRO_LIVE, "approved", approver="human_admin")
    return reg


def _arm(sid, capital=1_000_000):
    arm_mod.arm(sid, HUMAN_ADMIN, capital_limit=capital, paper_months=12)


def _signal(sid, direction, instrument="005930", strength=1.0):
    fusion_providers.PROVIDER_REGISTRY[sid] = lambda as_of="": [
        StrategySignal(strategy_id=sid, instrument=instrument, direction=direction, strength=strength)
    ]


def _flat_perf(monkeypatch):
    """모든 전략에 동일 양(+) 점수 부여 — weighting.py는 전 전략 score=0이면
    weight=0/net=0/direction=0이 되어 armed_backers 체크까지 못 감(실서비스에서도
    실제로 그런 상태 — 이건 fusion 로직 검증이 아니라 armed 필터 검증이 목적이므로 고정값으로 우회)."""
    monkeypatch.setattr(live_router, "perf_for", lambda sid: StrategyPerf(
        strategy_id=sid, score=1.0, sharpe=1.0, volatility=0.1,
        observation_count=30, underpowered=False, source="test"))


def test_no_armed_backer_never_routes(monkeypatch):
    _register_paper_active(SID)
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "no_armed_go_backer"


def test_armed_but_not_go_never_routes(monkeypatch):
    _register_paper_active(SID)
    _arm(SID)
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: False)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "no_armed_go_backer"


def test_armed_and_go_routes_with_paper_false(monkeypatch):
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)
    calls = []
    monkeypatch.setattr(live_router.broker_bridge, "route_order",
                         lambda o: calls.append(o) or {"status": "submitted"})
    r = live_router.route_all()
    assert len(r["routed"]) == 1
    assert calls[0] == {"venue": "KR", "symbol": "005930", "side": "BUY",
                         "quantity": 14, "order_type": "MARKET", "price": 70000.0,
                         "paper": False, "strategy_id": SID}


def test_broker_rejection_recorded_in_blocked_and_continues(monkeypatch):
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)

    def _reject(o):
        raise live_router.broker_bridge.BrokerOrderRejected("risk violation")
    monkeypatch.setattr(live_router.broker_bridge, "route_order", _reject)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "risk violation"


def test_two_agreeing_strategies_boost_size(monkeypatch):
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _register_paper_active(SID2)
    _arm(SID2, capital=1_000_000)
    _signal(SID, 1)
    fusion_providers.PROVIDER_REGISTRY[SID2] = lambda as_of="": [
        StrategySignal(strategy_id=SID2, instrument="005930", direction=1, strength=1.0)
    ]
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)
    monkeypatch.setitem(live_router.EDGE_PROVIDER_VENUE, SID2, "KR")
    calls = []
    monkeypatch.setattr(live_router.broker_bridge, "route_order",
                         lambda o: calls.append(o) or {"status": "submitted"})
    r = live_router.route_all()
    assert len(r["routed"]) == 1
    assert calls[0]["quantity"] > 14  # boosted (1.3x) vs single-strategy baseline of 14


def test_capital_too_small_for_one_share_is_blocked(monkeypatch):
    _register_paper_active(SID)
    _arm(SID, capital=100)  # 100원 / 70000원 주가 = 0주
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "unpriceable_or_too_small"


def test_no_signals_returns_empty_note():
    r = live_router.route_all()
    assert r["routed"] == [] and r["blocked"] == []
    assert "note" in r
