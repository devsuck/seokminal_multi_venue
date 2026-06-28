import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app)

# ── /orders/kr ────────────────────────────────────────────────────────────────

def test_place_kr_order_missing_credentials_returns_503():
    with patch.dict("os.environ", {
        "KIS_APP_KEY": "", "KIS_APP_SECRET": "",
        "KIS_CANO": "", "KIS_ACNT_PRDT_CD": "",
    }):
        r = client.post("/orders/kr", json={
            "code": "005930", "side": "BUY", "quantity": 1, "order_type": "MARKET",
        })
    assert r.status_code == 503


def test_place_kr_order_invalid_side_returns_400():
    with patch.dict("os.environ", {
        "KIS_APP_KEY": "k", "KIS_APP_SECRET": "s",
        "KIS_CANO": "c", "KIS_ACNT_PRDT_CD": "01",
    }):
        r = client.post("/orders/kr", json={
            "code": "005930", "side": "HOLD", "quantity": 1, "order_type": "MARKET",
        })
    assert r.status_code == 400


def test_place_kr_order_limit_without_price_returns_400():
    with patch.dict("os.environ", {
        "KIS_APP_KEY": "k", "KIS_APP_SECRET": "s",
        "KIS_CANO": "c", "KIS_ACNT_PRDT_CD": "01",
    }):
        r = client.post("/orders/kr", json={
            "code": "005930", "side": "BUY", "quantity": 1, "order_type": "LIMIT",
        })
    assert r.status_code == 400


@patch("api_server.main.KISOrderClient")
def test_place_kr_order_success(mock_cls):
    mock_client = MagicMock()
    mock_client.place_order.return_value = {
        "order_id": "0001234", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0,
    }
    mock_cls.return_value = mock_client

    with patch.dict("os.environ", {
        "KIS_APP_KEY": "k", "KIS_APP_SECRET": "s",
        "KIS_CANO": "c", "KIS_ACNT_PRDT_CD": "01",
    }):
        r = client.post("/orders/kr", json={
            "code": "005930", "side": "BUY", "quantity": 1, "order_type": "MARKET",
        })

    assert r.status_code == 200
    body = r.json()
    assert body["order_id"] == "0001234"
    assert body["status"] == "SUBMITTED"
    assert body["filled"] == 0.0
    assert body["remaining"] == 1.0


@patch("api_server.main.KISOrderClient")
def test_cancel_kr_order_success(mock_cls):
    mock_client = MagicMock()
    mock_client.cancel_order.return_value = {
        "order_id": "0001234", "status": "CANCELLED", "filled": 0.0, "remaining": 0.0,
    }
    mock_cls.return_value = mock_client

    with patch.dict("os.environ", {
        "KIS_APP_KEY": "k", "KIS_APP_SECRET": "s",
        "KIS_CANO": "c", "KIS_ACNT_PRDT_CD": "01",
    }):
        r = client.post("/orders/kr/0001234/cancel", json={
            "code": "005930", "quantity": 1,
        })

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "CANCELLED"
    assert body["order_id"] == "0001234"


@patch("api_server.main.KISOrderClient")
def test_get_kr_order_status_found(mock_cls):
    mock_client = MagicMock()
    mock_client.get_order_status.return_value = {
        "order_id": "0001234", "status": "FILLED", "filled": 1.0, "remaining": 0.0,
    }
    mock_cls.return_value = mock_client

    with patch.dict("os.environ", {
        "KIS_APP_KEY": "k", "KIS_APP_SECRET": "s",
        "KIS_CANO": "c", "KIS_ACNT_PRDT_CD": "01",
    }):
        r = client.get("/orders/kr/0001234/status", params={"date": "20260628"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FILLED"
    assert body["filled"] == 1.0


@patch("api_server.main.KISOrderClient")
def test_get_kr_order_status_not_found_returns_404(mock_cls):
    mock_client = MagicMock()
    mock_client.get_order_status.return_value = None
    mock_cls.return_value = mock_client

    with patch.dict("os.environ", {
        "KIS_APP_KEY": "k", "KIS_APP_SECRET": "s",
        "KIS_CANO": "c", "KIS_ACNT_PRDT_CD": "01",
    }):
        r = client.get("/orders/kr/9999999/status", params={"date": "20260628"})

    assert r.status_code == 404


@patch("api_server.main._load_bots")
def test_all_bots_live_status_empty_when_no_bots(mock_load):
    mock_load.return_value = {}
    r = client.get("/bots/all-live-status")
    assert r.status_code == 200
    body = r.json()
    assert body["bots"] == []
