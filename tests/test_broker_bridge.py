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


@pytest.fixture(autouse=True)
def _deadman_not_expired(monkeypatch):
    """데드맨 스위치는 이 파일의 관심사가 아님(tests/test_deadman.py가 전담) — 기본
    heartbeat 정상으로 고정해 기존 게이트 테스트들이 데드맨 차단으로 오염되지 않게 함."""
    monkeypatch.setattr(bb.deadman, "is_expired", lambda: False)


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
    # 크레덴셜 없으면 포지션 조회부터 실패 → _gate()가 place_order 도달 전에 fail-closed 거부.
    with pytest.raises(bb.BrokerOrderRejected, match="position lookup failed"):
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

        def get_holdings(self):
            return []

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

        def get_holdings(self):
            return []

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
    """실계좌(paper=False) 주문은 ADR 0004대로 여전히 차단."""
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: False)
    monkeypatch.setenv("KIS_APP_KEY", "k")
    monkeypatch.setenv("KIS_APP_SECRET", "s")
    monkeypatch.setenv("KIS_CANO", "c")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    with pytest.raises(bb.BrokerOrderRejected, match="live execution disabled"):
        bb.route_order(_kr_order(paper=False))


def test_paper_order_not_blocked_by_autonomy_level(monkeypatch):
    """페이퍼 주문(실리스크 0)은 AUTONOMY_LEVEL 게이트 우회 — risk_guard는 여전히 적용."""
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: False)
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "k")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "s")
    monkeypatch.setenv("KIS_MOCK_CANO", "c")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.setattr(
        bb.KISOrderClient, "place_order",
        lambda self, *a, **k: {"status": "ok"},
    )
    monkeypatch.setattr(bb.KISOrderClient, "get_holdings", lambda self: [])
    result = bb.route_order(_kr_order(paper=True))
    assert result == {"status": "ok"}


def test_route_close_blocked_when_autonomy_level_insufficient_real(monkeypatch):
    """실계좌(paper=False) 청산은 ADR 0004대로 여전히 차단."""
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: False)
    with pytest.raises(bb.BrokerOrderRejected, match="live execution disabled"):
        bb.route_close(venue="US_ALPACA", symbol="AAPL", paper=False)


def test_route_close_not_blocked_by_autonomy_level_for_paper(monkeypatch):
    """페이퍼 청산은 AUTONOMY_LEVEL 게이트 우회."""
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: False)

    class _FakePosition:
        def dict(self):
            return {"symbol": "AAPL", "status": "closed"}

    monkeypatch.setattr(
        "api_server.routers.alpaca_shared._trading_client",
        lambda paper: type("m", (), {"close_position": lambda self, s: _FakePosition()})(),
    )
    result = bb.route_close(venue="US_ALPACA", symbol="AAPL", paper=True)
    assert result == {"symbol": "AAPL", "status": "closed"}


def test_route_set_leverage_not_blocked_by_autonomy_level_for_paper(monkeypatch):
    """페이퍼 레버리지 설정은 AUTONOMY_LEVEL 게이트 우회."""
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: False)
    fake_trader = type("m", (), {})()
    fake_trader.set_leverage = lambda coin, leverage, is_cross, paper: {"status": "ok"}
    monkeypatch.setitem(__import__("sys").modules, "hyperliquid.trader", fake_trader)
    result = bb.route_set_leverage(coin="BTC", leverage=3, is_cross=True, paper=True)
    assert result == {"status": "ok"}
