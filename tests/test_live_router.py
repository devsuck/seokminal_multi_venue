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
    monkeypatch.setattr(live_router, "_kr_position_qty", lambda code: 0.0)
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
    monkeypatch.setattr(live_router, "_kr_position_qty", lambda code: 0.0)

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
    monkeypatch.setattr(live_router, "_kr_position_qty", lambda code: 0.0)
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
    monkeypatch.setattr(live_router, "_kr_position_qty", lambda code: 0.0)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "unpriceable_or_too_small"


def test_no_signals_returns_empty_note():
    r = live_router.route_all()
    assert r["routed"] == [] and r["blocked"] == []
    assert "note" in r


def test_zero_weight_armed_backer_alone_never_routes(monkeypatch):
    """C2 회귀 — armed+GO라도 weight=0인 기여자는 armed_backers에서 제외되어야 함.
    (letter만 통과: is_armed+edge_go는 만족하지만 fs.direction에 아무 기여도 없는
    zero-weight 백커가 진짜 트리거가 되면 안 됨). 브리프의 단일신호 스니펫은 그대로
    쓰면 score=0인 유일 기여자의 net도 0이 되어 fs.direction=0 → route_all의
    `if fs.direction==0: continue`에 걸려 blocked에 아예 안 잡힘(weighting.py의
    zero-total 분기 + fusion.py의 _sign(0)=0을 실제로 확인해서 조정) — 그래서
    양(+)weight인데 unarmed인 두번째 백커를 같은 방향에 추가해 fs.direction을
    비-zero로 만들고, 그 상태에서도 armed_backers가 비어야 함을 검증한다."""
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _signal(SID, 1)
    _register_paper_active(SID2)  # armed 안 함 — unarmed 양(+)weight 백커
    fusion_providers.PROVIDER_REGISTRY[SID2] = lambda as_of="": [
        StrategySignal(strategy_id=SID2, instrument="005930", direction=1, strength=1.0)
    ]

    def _perf(sid):
        score = 0.0 if sid == SID else 1.0
        return StrategyPerf(strategy_id=sid, score=score, sharpe=score, volatility=0.1,
                             observation_count=30, underpowered=(sid == SID), source="test")
    monkeypatch.setattr(live_router, "perf_for", _perf)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "no_armed_go_backer"


def test_already_holding_position_blocks_duplicate_buy(monkeypatch):
    """C1 회귀 — 실보유 수량>0이면 동일 방향(BUY) 중복주문을 broker에 보내지 않고
    차단해야 함(멱등성)."""
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)
    monkeypatch.setattr(live_router, "_kr_position_qty", lambda code: 5.0)
    calls = []
    monkeypatch.setattr(live_router.broker_bridge, "route_order",
                         lambda o: calls.append(o) or {"status": "submitted"})
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "already_holding"
    assert calls == []


def test_one_instrument_error_does_not_abort_batch(monkeypatch):
    """I4 회귀 — 한 계기(005930)의 broker_bridge.route_order가
    BrokerOrderRejected가 아닌 일반 예외(RuntimeError)를 던져도 나머지 계기
    (000660)는 계속 라우팅되어야 함(배치 전체 중단 금지)."""
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _register_paper_active(SID2)
    _arm(SID2, capital=1_000_000)
    _signal(SID, 1, instrument="005930")
    fusion_providers.PROVIDER_REGISTRY[SID2] = lambda as_of="": [
        StrategySignal(strategy_id=SID2, instrument="000660", direction=1, strength=1.0)
    ]
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)
    monkeypatch.setattr(live_router, "_kr_position_qty", lambda code: 0.0)
    monkeypatch.setitem(live_router.EDGE_PROVIDER_VENUE, SID2, "KR")

    def _route(o):
        if o["symbol"] == "005930":
            raise RuntimeError("kis blew up")
        return {"status": "submitted"}
    monkeypatch.setattr(live_router.broker_bridge, "route_order", _route)
    r = live_router.route_all()
    assert len(r["routed"]) == 1
    assert r["routed"][0]["instrument"] == "000660"
    assert len(r["blocked"]) == 1
    assert r["blocked"][0]["instrument"] == "005930"
    assert r["blocked"][0]["reason"] == "error: kis blew up"


def test_boost_requires_same_direction_agreement_not_raw_count(monkeypatch):
    """I1 회귀 — 반대방향 신호가 있어 fs.n_strategies=2가 되어도 same_direction_n=1
    이면 부스트(1.3x)가 발동하면 안 됨. 구코드(fs.n_strategies>=2)라면 방향 무관하게
    발동해 수량이 18(=1.3x)이 됐을 상황을 14(무부스트 베이스라인)로 고정해 검증.

    브리프의 e.g.(score 2.0/1.0)를 그대로 쓰면 반대방향 기여자의 weight가 1/3로
    커서 confidence=1/3이 되어 baseline 14가 아니라 4가 나옴(직접 계산 후 확인) —
    반대방향 기여자의 weight를 1%로 줄여(score 99.0/1.0) confidence=0.98로 만들어
    "양(+)weight인 진짜 반대방향 표"를 유지하면서도 int(1,000,000*0.98//70000)=14로
    떨어지게 조정."""
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _register_paper_active(SID2)
    _signal(SID, 1)
    fusion_providers.PROVIDER_REGISTRY[SID2] = lambda as_of="": [
        StrategySignal(strategy_id=SID2, instrument="005930", direction=-1, strength=1.0)
    ]

    def _perf(sid):
        score = 99.0 if sid == SID else 1.0
        return StrategyPerf(strategy_id=sid, score=score, sharpe=score, volatility=0.1,
                             observation_count=30, underpowered=False, source="test")
    monkeypatch.setattr(live_router, "perf_for", _perf)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)
    monkeypatch.setattr(live_router, "_kr_position_qty", lambda code: 0.0)
    calls = []
    monkeypatch.setattr(live_router.broker_bridge, "route_order",
                         lambda o: calls.append(o) or {"status": "submitted"})
    r = live_router.route_all()
    assert len(r["routed"]) == 1
    assert calls[0]["quantity"] == 14  # NOT boosted (would be 18 under the n_strategies>=2 bug)
