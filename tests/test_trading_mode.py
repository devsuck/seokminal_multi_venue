"""Trading mode + risk snapshot endpoint."""
from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app)


def test_mode_defaults_to_paper(monkeypatch):
    monkeypatch.delenv("IB_PORT", raising=False)
    monkeypatch.setenv("KIS_MOCK", "true")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    r = client.get("/trading/mode")
    assert r.status_code == 200
    body = r.json()
    assert body["venues"]["US"]["mode"] == "paper"
    assert body["venues"]["KR"]["mode"] == "paper"
    assert body["any_live"] is False


def test_mode_detects_live_ib_port(monkeypatch):
    monkeypatch.setenv("IB_PORT", "7496")
    r = client.get("/trading/mode")
    body = r.json()
    assert body["venues"]["US"]["mode"] == "live"
    assert body["any_live"] is True


def test_mode_includes_risk_limits(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_QTY", "123")
    monkeypatch.setenv("TRADING_KILL_SWITCH", "true")
    r = client.get("/trading/mode")
    body = r.json()
    assert body["risk"]["max_order_qty"] == 123
    assert body["risk"]["kill_switch"] is True
