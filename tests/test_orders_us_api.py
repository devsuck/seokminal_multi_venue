import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app)


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
    mock_inst.close = AsyncMock()
    mock_cls.return_value = mock_inst

    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": 1, "order_type": "MARKET",
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
