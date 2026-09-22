import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from api_server.main import app, _hl_current_position_qty

client = TestClient(app, client=("127.0.0.1", 1))


def test_place_us_order_invalid_side_returns_400():
    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "HOLD", "quantity": 1, "order_type": "MARKET",
    })
    assert r.status_code == 400


def test_place_us_order_limit_without_price_returns_400():
    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": 1, "order_type": "LIMIT",
    })
    assert r.status_code == 400


@patch("api_server.main.IBOrderClient")
def test_place_us_order_success(mock_cls):
    mock_inst = MagicMock()
    mock_inst.place_order = AsyncMock(return_value={
        "order_id": 42, "status": "PendingSubmit", "filled": 0.0, "remaining": 1.0,
    })
    mock_inst.get_positions = AsyncMock(return_value=[])
    mock_inst.close = AsyncMock()
    mock_cls.return_value = mock_inst

    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": 1, "order_type": "MARKET",
        "paper": False,  # IB(TWS) live path (paper=True → Alpaca)
    })
    assert r.status_code == 200
    body = r.json()
    assert body["order_id"] == 42
    assert body["status"] == "PendingSubmit"
    assert body["filled"] == 0.0
    assert body["remaining"] == 1.0


@patch("api_server.main.IBOrderClient")
def test_cancel_us_order_success(mock_cls):
    mock_inst = MagicMock()
    mock_inst.cancel_order = AsyncMock(return_value={
        "order_id": 42, "status": "ApiCancelled", "filled": 0.0, "remaining": 1.0,
    })
    mock_inst.close = AsyncMock()
    mock_cls.return_value = mock_inst

    r = client.post("/orders/us/42/cancel")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ApiCancelled"
    assert body["order_id"] == 42


@patch("api_server.main.IBOrderClient")
def test_get_us_order_status_found(mock_cls):
    mock_inst = MagicMock()
    mock_inst.get_order_status = AsyncMock(return_value={
        "order_id": 42, "status": "Filled", "filled": 1.0, "remaining": 0.0,
    })
    mock_inst.close = AsyncMock()
    mock_cls.return_value = mock_inst

    r = client.get("/orders/us/42/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "Filled"
    assert body["filled"] == 1.0


@patch("api_server.main.IBOrderClient")
def test_get_us_order_status_not_found_returns_404(mock_cls):
    mock_inst = MagicMock()
    mock_inst.get_order_status = AsyncMock(return_value=None)
    mock_inst.close = AsyncMock()
    mock_cls.return_value = mock_inst

    r = client.get("/orders/us/9999/status")
    assert r.status_code == 404


@patch("api_server.main.IBOrderClient")
def test_place_us_order_blocked_when_existing_ib_position_breaches_cap(mock_cls, monkeypatch):
    """Position cap must see the real IB-reported position, not an assumed
    0 — regression for the cap being neutered on the US live order path."""
    monkeypatch.setenv("MAX_POSITION_QTY", "100")
    mock_inst = MagicMock()
    mock_inst.get_positions = AsyncMock(return_value=[{"symbol": "AAPL", "qty": 90.0, "avg_price": 100.0}])
    mock_inst.close = AsyncMock()
    mock_cls.return_value = mock_inst

    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": 20, "order_type": "MARKET",
        "paper": False,
    })
    assert r.status_code == 422
    mock_inst.place_order.assert_not_called()


def test_hl_current_position_qty_finds_matching_coin(monkeypatch):
    monkeypatch.setattr(
        "hyperliquid.trader.get_positions",
        lambda paper: {"asset_positions": [
            {"position": {"coin": "BTC", "szi": "1.5"}},
            {"position": {"coin": "ETH", "szi": "-2.0"}},
        ]},
    )
    assert _hl_current_position_qty("BTC", paper=True) == 1.5
    assert _hl_current_position_qty("ETH", paper=True) == -2.0
    assert _hl_current_position_qty("SOL", paper=True) == 0.0


def test_hl_current_position_qty_fails_closed_on_lookup_error(monkeypatch):
    def _boom(paper):
        raise RuntimeError("API down")
    monkeypatch.setattr("hyperliquid.trader.get_positions", _boom)
    assert _hl_current_position_qty("BTC", paper=True) is None


@patch("api_server.main.IBOrderClient")
def test_cancel_us_order_paper_false_uses_live_port_7496(mock_cls):
    """cancel/status must follow the original order's mode, not always the
    paper port — regression for IB TWS port mismatch on live US orders."""
    mock_inst = MagicMock()
    mock_inst.cancel_order = AsyncMock(return_value={
        "order_id": 42, "status": "ApiCancelled", "filled": 0.0, "remaining": 1.0,
    })
    mock_inst.close = AsyncMock()
    mock_cls.return_value = mock_inst

    r = client.post("/orders/us/42/cancel", params={"paper": False})
    assert r.status_code == 200
    assert mock_cls.call_args.kwargs["port"] == 7496


@patch("api_server.main.IBOrderClient")
def test_cancel_us_order_paper_default_uses_paper_port_7497(mock_cls):
    mock_inst = MagicMock()
    mock_inst.cancel_order = AsyncMock(return_value={
        "order_id": 42, "status": "ApiCancelled", "filled": 0.0, "remaining": 1.0,
    })
    mock_inst.close = AsyncMock()
    mock_cls.return_value = mock_inst

    r = client.post("/orders/us/42/cancel")
    assert r.status_code == 200
    assert mock_cls.call_args.kwargs["port"] == 7497


@patch("api_server.main.IBOrderClient")
def test_get_us_order_status_paper_false_uses_live_port_7496(mock_cls):
    mock_inst = MagicMock()
    mock_inst.get_order_status = AsyncMock(return_value={
        "order_id": 42, "status": "Filled", "filled": 1.0, "remaining": 0.0,
    })
    mock_inst.close = AsyncMock()
    mock_cls.return_value = mock_inst

    r = client.get("/orders/us/42/status", params={"paper": False})
    assert r.status_code == 200
    assert mock_cls.call_args.kwargs["port"] == 7496
