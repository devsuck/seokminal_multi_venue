"""Order-endpoint risk wiring: rejections must happen before any broker call."""
from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app)


def test_us_order_zero_quantity_rejected_by_schema():
    # Field(gt=0) -> pydantic 422 before the handler / broker is touched
    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": 0, "order_type": "MARKET",
    })
    assert r.status_code == 422


def test_us_order_negative_quantity_rejected_by_schema():
    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": -3, "order_type": "MARKET",
    })
    assert r.status_code == 422


def test_us_order_over_qty_cap_blocked_by_risk_guard(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_QTY", "100")
    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": 500, "order_type": "MARKET",
    })
    assert r.status_code == 422
    assert "risk check failed" in r.json()["detail"]


def test_us_order_over_notional_cap_blocked(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_QTY", "100000")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1000")
    # LIMIT order gives the guard a price -> notional = 50 * 100 = 5000 > 1000
    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": 50, "order_type": "LIMIT",
        "limit_price": 100.0,
    })
    assert r.status_code == 422
    assert "notional" in r.json()["detail"]


def test_kill_switch_blocks_us_order(monkeypatch):
    monkeypatch.setenv("TRADING_KILL_SWITCH", "true")
    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": 1, "order_type": "MARKET",
    })
    assert r.status_code == 422
    assert "kill switch" in r.json()["detail"]
