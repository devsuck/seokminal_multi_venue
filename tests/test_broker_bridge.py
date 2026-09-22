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


def test_kr_order_recorded_to_oms_and_order_audit(monkeypatch, tmp_path):
    """회귀: Fork C Finding 5 — route_order로 나간 봇 주문이 dashboard 실현손익/
    /orders/audit·/orders/oms가 읽는 api_server.oms·order_audit에 안 남으면
    체결이 있어도 대시보드에서 완전히 안 보임."""
    from api_server import oms
    monkeypatch.setattr(oms, "_orders", {})
    monkeypatch.setenv("ORDER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
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
            return {"order_id": "ORD123", "status": "SUBMITTED", "filled": 0.0, "remaining": float(qty)}

    monkeypatch.setattr(bb, "KISOrderClient", _FakeClient)
    bb.route_order(_kr_order())

    order = oms.get_order("KR", "ORD123")
    assert order is not None
    assert order["symbol"] == "005930"
    assert order["side"] == "BUY"

    from api_server.order_audit import read_recent
    entries = read_recent(path=tmp_path / "audit.jsonl")
    assert len(entries) == 1
    assert entries[0]["venue"] == "KR"
    assert entries[0]["result"]["order_id"] == "ORD123"


def test_us_alpaca_order_recorded_to_oms_maps_id_and_filled_qty(monkeypatch, tmp_path):
    """_fmt_order()는 id/filled_qty 키를 쓰는데 oms.record_event는 order_id/filled를
    읽음 — 매핑 안 하면 US_ALPACA 주문은 oms.record_event가 조용히 no-op됨."""
    from api_server import oms
    monkeypatch.setattr(oms, "_orders", {})
    monkeypatch.setenv("ORDER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: True)

    class _FakeOrder:
        id = "abc-123"
        symbol = "AAPL"
        side = type("S", (), {"value": "buy"})()
        qty = 1.0
        filled_qty = 1.0
        status = type("St", (), {"value": "filled"})()
        filled_avg_price = 150.0
        created_at = None

    class _FakeClient:
        def submit_order(self, req):
            return _FakeOrder()

    monkeypatch.setattr(
        "api_server.routers.alpaca_shared._trading_client",
        lambda paper: _FakeClient(),
    )
    order = dict(venue="US_ALPACA", symbol="AAPL", side="BUY", quantity=1,
                 order_type="market", price=None, paper=True)
    bb.route_order(order)

    recorded = oms.get_order("US_ALPACA", "abc-123")
    assert recorded is not None
    assert recorded["status"] == "FILLED"
    assert recorded["price"] == 150.0


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


def test_route_order_blocked_when_own_venue_killed(monkeypatch):
    monkeypatch.setattr(
        "api_server.risk_state.is_killed",
        lambda venue: venue == "KR",
    )
    with pytest.raises(bb.BrokerOrderRejected):
        bb.route_order(_kr_order())


def test_route_order_not_blocked_when_different_venue_killed(monkeypatch):
    """KR이 죽어도 HL 같은 무관한 venue는 막히면 안 됨 — 교차오염 없음 확인."""
    monkeypatch.setattr(
        "api_server.risk_state.is_killed",
        lambda venue: venue == "HL",
    )
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


async def test_route_order_ib_blocked_when_us_ib_killed(monkeypatch):
    monkeypatch.setattr(
        "api_server.risk_state.is_killed",
        lambda venue: venue == "US_IB",
    )

    class _FakeIBClient:
        async def place_order(self, *a, **kw):
            raise AssertionError("차단됐어야 함 — 브로커 호출까지 가면 안 됨")

    with pytest.raises(bb.BrokerOrderRejected):
        await bb.route_order_ib(
            {"symbol": "AAPL", "side": "BUY", "quantity": 1, "paper": True},
            _FakeIBClient(),
        )
