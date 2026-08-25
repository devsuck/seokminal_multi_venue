"""broker_bridge.route_order — Gateway 통과 후 실주문 단계. risk_guard 이중 체크,
KR/HL 분기, 크레덴셜 부재 시 거부, 알림 발송. 실브로커 호출은 전부 monkeypatch."""
from __future__ import annotations

import pytest

from jarvis.execution import broker_bridge as bb


@pytest.fixture(autouse=True)
def _no_real_notify(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api_server.lv6_notify.notify_live_trade",
        lambda **kw: calls.append(kw),
    )
    return calls


@pytest.fixture(autouse=True)
def _reset_tracker(monkeypatch):
    monkeypatch.setattr(bb, "_daily_pnl", None)


@pytest.fixture(autouse=True)
def _allow_live_execution(monkeypatch):
    """기본값: 게이트 통과. 개별 테스트가 False로 덮어쓰면 그 테스트만 차단됨."""
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: True)


def _kr_order(**over):
    o = dict(venue="KR", symbol="005930", side="BUY", quantity=1,
             order_type="MARKET", price=70000, paper=True)
    o.update(over)
    return o


def test_kr_rejected_when_risk_violates(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_QTY_KR", "0")
    with pytest.raises(bb.BrokerOrderRejected):
        bb.route_order(_kr_order())


def test_kr_rejected_when_no_mock_credentials(monkeypatch):
    for v in ("KIS_MOCK_APP_KEY", "KIS_MOCK_APP_SECRET", "KIS_MOCK_CANO", "KIS_ACNT_PRDT_CD"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.delenv("MAX_ORDER_QTY_KR", raising=False)
    with pytest.raises(bb.BrokerOrderRejected, match="credentials"):
        bb.route_order(_kr_order())


def test_kr_places_order_and_notifies(monkeypatch, _no_real_notify):
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "k")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "s")
    monkeypatch.setenv("KIS_MOCK_CANO", "c")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.delenv("MAX_ORDER_QTY_KR", raising=False)

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def place_order(self, symbol, side, qty, order_type, price):
            return {"status": "filled", "symbol": symbol}

    monkeypatch.setattr(bb, "KISOrderClient", _FakeClient)
    result = bb.route_order(_kr_order())
    assert result["status"] == "filled"
    assert len(_no_real_notify) == 1
    assert _no_real_notify[0]["venue"] == "KR"


def test_hl_places_order_and_notifies(monkeypatch, _no_real_notify):
    monkeypatch.delenv("MAX_ORDER_QTY_HL", raising=False)
    fake_trader = type("m", (), {})()
    fake_trader.place_order = lambda **kw: {"status": "filled", "coin": kw["coin"]}
    monkeypatch.setitem(__import__("sys").modules, "hyperliquid.trader", fake_trader)

    order = dict(venue="HL", symbol="BTC", side="BUY", quantity=0.001,
                 order_type="market", price=60000, paper=True)
    result = bb.route_order(order)
    assert result["status"] == "filled"
    assert len(_no_real_notify) == 1
    assert _no_real_notify[0]["venue"] == "HL"


def test_notify_failure_does_not_mislabel_submitted_order(monkeypatch):
    """주문 제출 성공 후 감사기록/알림이 터져도 route_order는 성공 result를 반환해야 함
    (호출부가 이미 나간 주문을 blocked로 오기록하는 사고 방지)."""
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "k")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "s")
    monkeypatch.setenv("KIS_MOCK_CANO", "c")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.delenv("MAX_ORDER_QTY_KR", raising=False)

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def place_order(self, symbol, side, qty, order_type, price):
            return {"status": "filled", "symbol": symbol}

    monkeypatch.setattr(bb, "KISOrderClient", _FakeClient)
    monkeypatch.setattr(
        "api_server.lv6_notify.notify_live_trade",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("telegram down")),
    )
    result = bb.route_order(_kr_order())
    assert result["status"] == "filled"


def test_unknown_venue_rejected():
    with pytest.raises(bb.BrokerOrderRejected, match="unknown venue"):
        bb.route_order(_kr_order(venue="US"))


def test_blocked_when_autonomy_level_insufficient(monkeypatch):
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: False)
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "k")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "s")
    monkeypatch.setenv("KIS_MOCK_CANO", "c")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    with pytest.raises(bb.BrokerOrderRejected, match="live execution disabled"):
        bb.route_order(_kr_order())
