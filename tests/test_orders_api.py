import asyncio
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app, client=("127.0.0.1", 1))

# 풀링된 IB 클라이언트/멱등성 캐시 리셋은 conftest.py의 전역 autouse 픽스처가 처리.

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
def test_place_kr_order_concurrent_same_client_order_id_only_submits_once(mock_cls):
    """동시 재시도(같은 client_order_id)가 idempotency 캐시 체크와 브로커 제출 사이
    경합해 중복 제출되는 것을 막는 회귀 — venue lock이 체크→제출→저장 구간을 직렬화."""
    calls = []

    def _slow_place_order(*a, **k):
        time.sleep(0.05)  # 경합 윈도우 넓히기
        calls.append(1)
        return {"order_id": "0001234", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0}

    mock_client = MagicMock()
    mock_client.place_order.side_effect = _slow_place_order
    mock_cls.return_value = mock_client

    results = []

    def _post():
        with patch.dict("os.environ", {
            "KIS_APP_KEY": "k", "KIS_APP_SECRET": "s",
            "KIS_CANO": "c", "KIS_ACNT_PRDT_CD": "01",
        }):
            results.append(client.post("/orders/kr", json={
                "code": "005930", "side": "BUY", "quantity": 1, "order_type": "MARKET",
                "client_order_id": "dup-kr-race",
            }))

    t1 = threading.Thread(target=_post)
    t2 = threading.Thread(target=_post)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert len(calls) == 1
    assert all(r.status_code == 200 for r in results)
    assert results[0].json() == results[1].json()


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
            "code": "005930", "quantity": 1, "paper": False,
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
        r = client.get("/orders/kr/0001234/status", params={"date": "20260628", "paper": False})

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
        r = client.get("/orders/kr/9999999/status", params={"date": "20260628", "paper": False})

    assert r.status_code == 404


@patch("api_server.main.KISOrderClient")
def test_place_kr_order_idempotent_retry_does_not_resubmit(mock_cls):
    mock_client = MagicMock()
    mock_client.place_order.return_value = {
        "order_id": "0001234", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0,
    }
    mock_cls.return_value = mock_client

    body = {
        "code": "005930", "side": "BUY", "quantity": 1, "order_type": "MARKET",
        "client_order_id": "retry-key-1",
    }
    with patch.dict("os.environ", {
        "KIS_APP_KEY": "k", "KIS_APP_SECRET": "s",
        "KIS_CANO": "c", "KIS_ACNT_PRDT_CD": "01",
    }):
        r1 = client.post("/orders/kr", json=body)
        r2 = client.post("/orders/kr", json=body)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    mock_client.place_order.assert_called_once()  # 두 번째 요청은 캐시에서 응답, 재주문 없음


def test_cancel_kr_order_paper_true_uses_mock_creds_not_live():
    """paper=True(default) must route to KIS_MOCK_* creds, not the live
    KIS_* creds — regression for cancel always hitting the live account
    regardless of the original order's mode."""
    with patch.dict("os.environ", {
        "KIS_APP_KEY": "live-k", "KIS_APP_SECRET": "live-s",
        "KIS_CANO": "live-c", "KIS_ACNT_PRDT_CD": "01",
        "KIS_MOCK_APP_KEY": "", "KIS_MOCK_APP_SECRET": "",
        "KIS_MOCK_CANO": "", "KIS_MOCK_ACNT_PRDT_CD": "",
    }, clear=False):
        r = client.post("/orders/kr/0001234/cancel", json={"code": "005930", "quantity": 1})
    assert r.status_code == 503  # mock creds missing -> refuses, proving it didn't silently use live


@patch("api_server.main.KISOrderClient")
def test_get_kr_order_status_paper_true_uses_mock_creds_not_live(mock_cls):
    with patch.dict("os.environ", {
        "KIS_APP_KEY": "live-k", "KIS_APP_SECRET": "live-s",
        "KIS_CANO": "live-c", "KIS_ACNT_PRDT_CD": "01",
        "KIS_MOCK_APP_KEY": "", "KIS_MOCK_APP_SECRET": "",
        "KIS_MOCK_CANO": "", "KIS_MOCK_ACNT_PRDT_CD": "",
    }, clear=False):
        r = client.get("/orders/kr/0001234/status", params={"date": "20260628"})
    assert r.status_code == 503


@patch("api_server.main.KISOrderClient")
def test_place_kr_order_shows_up_in_oms(mock_cls):
    mock_client = MagicMock()
    mock_client.place_order.return_value = {
        "order_id": "0005555", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0,
    }
    mock_cls.return_value = mock_client

    with patch.dict("os.environ", {
        "KIS_APP_KEY": "k", "KIS_APP_SECRET": "s",
        "KIS_CANO": "c", "KIS_ACNT_PRDT_CD": "01",
    }):
        client.post("/orders/kr", json={
            "code": "005930", "side": "BUY", "quantity": 1, "order_type": "MARKET",
        })

    r = client.get("/orders/oms", params={"venue": "KR"})
    assert r.status_code == 200
    orders = r.json()["orders"]
    assert len(orders) == 1
    assert orders[0]["order_id"] == "0005555"
    assert orders[0]["status"] == "OPEN"


# ── /orders/us ───────────────────────────────────────────────────────────────

@patch("api_server.main.IBOrderClient")
def test_place_us_order_live_ib_success(mock_cls):
    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(return_value={
        "order_id": 501, "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0, "avg_fill_price": None,
    })
    mock_client.get_positions = AsyncMock(return_value=[])
    mock_cls.return_value = mock_client

    r = client.post("/orders/us", json={
        "symbol": "AAPL", "side": "BUY", "quantity": 1, "order_type": "MARKET", "paper": False,
    })

    assert r.status_code == 200
    assert r.json()["order_id"] == 501


@patch("api_server.main.IBOrderClient")
def test_place_us_order_reuses_pooled_ib_client_across_requests(mock_cls):
    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(return_value={
        "order_id": 501, "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0, "avg_fill_price": None,
    })
    mock_client.get_positions = AsyncMock(return_value=[])
    mock_cls.return_value = mock_client

    for _ in range(2):
        r = client.post("/orders/us", json={
            "symbol": "AAPL", "side": "BUY", "quantity": 1, "order_type": "MARKET", "paper": False,
        })
        assert r.status_code == 200

    mock_cls.assert_called_once()  # 같은 (host,port,client_id) 재사용 — 매 요청 재연결 없음
    assert mock_client.place_order.await_count == 2  # 풀링돼도 각 주문은 실제로 제출됨


@patch("api_server.main.IBOrderClient")
def test_place_us_order_idempotent_retry_does_not_resubmit(mock_cls):
    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(return_value={
        "order_id": 501, "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0, "avg_fill_price": None,
    })
    mock_client.get_positions = AsyncMock(return_value=[])
    mock_cls.return_value = mock_client

    body = {
        "symbol": "AAPL", "side": "BUY", "quantity": 1, "order_type": "MARKET", "paper": False,
        "client_order_id": "retry-key-us",
    }
    r1 = client.post("/orders/us", json=body)
    r2 = client.post("/orders/us", json=body)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert mock_client.place_order.await_count == 1


@patch("api_server.main.IBOrderClient")
def test_place_us_order_concurrent_same_client_order_id_only_submits_once(mock_cls):
    """동시 재시도(같은 client_order_id)가 idempotency 캐시 체크와 브로커 제출 사이
    경합해 중복 제출되는 것을 막는 회귀 — venue lock이 체크→제출→저장 구간을 직렬화."""
    calls = []

    async def _slow_place_order(*a, **k):
        await asyncio.sleep(0.05)  # 경합 윈도우 넓히기
        calls.append(1)
        return {"order_id": 501, "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0, "avg_fill_price": None}

    mock_client = MagicMock()
    mock_client.place_order = AsyncMock(side_effect=_slow_place_order)
    mock_client.get_positions = AsyncMock(return_value=[])
    mock_cls.return_value = mock_client

    body = {
        "symbol": "AAPL", "side": "BUY", "quantity": 1, "order_type": "MARKET", "paper": False,
        "client_order_id": "dup-us-race",
    }
    results = []

    def _post(c):
        results.append(c.post("/orders/us", json=body))

    # bare module-level `client` gives each call its own throwaway event loop
    # (Starlette TestClient portal_factory) — two threads would run on two
    # separate loops and never actually contend for the same asyncio.Lock.
    # A `with`-entered client keeps one shared portal/loop for real concurrency.
    with TestClient(app, client=("127.0.0.1", 1)) as shared_client:
        t1 = threading.Thread(target=_post, args=(shared_client,))
        t2 = threading.Thread(target=_post, args=(shared_client,))
        t1.start(); t2.start()
        t1.join(); t2.join()

    assert len(calls) == 1
    assert all(r.status_code == 200 for r in results)
    assert results[0].json() == results[1].json()


# ── /orders/options ──────────────────────────────────────────────────────────

@patch("api_server.main.IBOrderClient")
def test_place_option_order_success(mock_cls):
    mock_client = MagicMock()
    mock_client.place_option_order = AsyncMock(return_value={
        "order_id": 701, "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0, "avg_fill_price": None,
    })
    mock_client.get_positions = AsyncMock(return_value=[])
    mock_cls.return_value = mock_client

    r = client.post("/orders/options", json={
        "symbol": "AAPL", "expiry": "20261218", "strike": 200.0, "right": "C",
        "side": "BUY", "quantity": 1, "order_type": "MARKET", "paper": True,
    })

    assert r.status_code == 200
    assert r.json()["order_id"] == 701


@patch("api_server.main.IBOrderClient")
def test_place_option_order_idempotent_retry_does_not_resubmit(mock_cls):
    mock_client = MagicMock()
    mock_client.place_option_order = AsyncMock(return_value={
        "order_id": 701, "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0, "avg_fill_price": None,
    })
    mock_client.get_positions = AsyncMock(return_value=[])
    mock_cls.return_value = mock_client

    body = {
        "symbol": "AAPL", "expiry": "20261218", "strike": 200.0, "right": "C",
        "side": "BUY", "quantity": 1, "order_type": "MARKET", "paper": True,
        "client_order_id": "retry-key-opt",
    }
    r1 = client.post("/orders/options", json=body)
    r2 = client.post("/orders/options", json=body)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert mock_client.place_option_order.await_count == 1


@patch("api_server.main.IBOrderClient")
def test_place_option_order_blocked_when_existing_ib_position_breaches_cap(mock_cls, monkeypatch):
    """Position cap must see the real IB-reported position, not an assumed
    0 — regression for the cap being neutered on the options order path."""
    monkeypatch.setenv("MAX_POSITION_QTY", "5")
    mock_client = MagicMock()
    mock_client.get_positions = AsyncMock(return_value=[{"symbol": "AAPL", "qty": 4.0, "avg_price": 2.0}])
    mock_cls.return_value = mock_client

    r = client.post("/orders/options", json={
        "symbol": "AAPL", "expiry": "20261218", "strike": 200.0, "right": "C",
        "side": "BUY", "quantity": 3, "order_type": "MARKET", "paper": True,
    })
    assert r.status_code == 422
    mock_client.place_option_order.assert_not_called()


@patch("api_server.main.IBOrderClient")
def test_cancel_option_order_paper_false_uses_live_port_7496(mock_cls):
    """cancel/status must follow the original order's mode, not always the
    paper port — regression for IB TWS port mismatch on live option orders."""
    mock_client = MagicMock()
    mock_client.cancel_order = AsyncMock(return_value={
        "order_id": 701, "status": "ApiCancelled", "filled": 0.0, "remaining": 1.0,
    })
    mock_cls.return_value = mock_client

    r = client.post("/orders/options/701/cancel", params={"paper": False})
    assert r.status_code == 200
    assert mock_cls.call_args.kwargs["port"] == 7496


@patch("api_server.main.IBOrderClient")
def test_cancel_option_order_paper_default_uses_paper_port_7497(mock_cls):
    mock_client = MagicMock()
    mock_client.cancel_order = AsyncMock(return_value={
        "order_id": 701, "status": "ApiCancelled", "filled": 0.0, "remaining": 1.0,
    })
    mock_cls.return_value = mock_client

    r = client.post("/orders/options/701/cancel")
    assert r.status_code == 200
    assert mock_cls.call_args.kwargs["port"] == 7497


@patch("api_server.main.IBOrderClient")
def test_get_option_order_status_paper_false_uses_live_port_7496(mock_cls):
    mock_client = MagicMock()
    mock_client.get_order_status = AsyncMock(return_value={
        "order_id": 701, "status": "Filled", "filled": 1.0, "remaining": 0.0,
    })
    mock_cls.return_value = mock_client

    r = client.get("/orders/options/701/status", params={"paper": False})
    assert r.status_code == 200
    assert mock_cls.call_args.kwargs["port"] == 7496


@patch("api_server.main._load_bots")
def test_all_bots_live_status_empty_when_no_bots(mock_load):
    mock_load.return_value = {}
    r = client.get("/bots/all-live-status")
    assert r.status_code == 200
    body = r.json()
    assert body["bots"] == []
