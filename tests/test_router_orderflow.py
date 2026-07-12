import asyncio
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_server.router_orderflow import router


class _StubManager:
    def __init__(self, symbols=None, subscribe_result=None):
        self._symbols = symbols or []
        self._subscribe_result = subscribe_result
        self.unsubscribed: list[tuple[str, object]] = []

    def active_symbols(self):
        return self._symbols

    def subscribe(self, symbol):
        return self._subscribe_result

    def unsubscribe(self, symbol, queue):
        self.unsubscribed.append((symbol, queue))


def _app():
    app = FastAPI()
    app.include_router(router)
    return app


def test_get_symbols_returns_manager_active_list():
    stub = _StubManager(symbols=["BTC.HL", "NQ"])
    client = TestClient(_app())
    with patch("api_server.router_orderflow.default_manager", stub):
        r = client.get("/orderflow/symbols")
    assert r.status_code == 200
    assert r.json() == {"symbols": ["BTC.HL", "NQ"]}


def test_ws_orderflow_sends_snapshot_then_queued_delta_then_cleans_up_on_disconnect():
    queue = asyncio.Queue()
    queue.put_nowait({"type": "footprint_delta", "bucket_ts": 0.0, "price": 100.0, "side": "buy", "delta_vol": 1.0})
    snapshot = {"footprint": [], "heatmap": []}
    stub = _StubManager(subscribe_result=(queue, snapshot))
    client = TestClient(_app())

    with patch("api_server.router_orderflow.default_manager", stub):
        with client.websocket_connect("/ws/orderflow/BTC.HL") as ws:
            first = ws.receive_json()
            second = ws.receive_json()

    assert first == {"type": "snapshot", "symbol": "BTC.HL", "footprint": [], "heatmap": []}
    assert second["type"] == "footprint_delta"
    assert stub.unsubscribed == [("BTC.HL", queue)]


def test_get_funding_returns_cached_snapshot():
    cached = {"coin": "BTC", "funding": 0.0001, "open_interest": 5000.0,
              "mark_px": 95000.0, "prev_day_px": 93000.0, "day_ntl_vlm": 5e8, "updated_at": 1000.0}
    client = TestClient(_app())
    with patch("api_server.router_orderflow.get_cached_funding", return_value=cached):
        r = client.get("/orderflow/funding/BTC")
    assert r.status_code == 200
    assert r.json() == cached


def test_get_funding_returns_zeroed_snapshot_when_not_cached_yet():
    client = TestClient(_app())
    with patch("api_server.router_orderflow.get_cached_funding", return_value=None):
        r = client.get("/orderflow/funding/DOGE")
    assert r.json() == {
        "coin": "DOGE", "funding": 0.0, "open_interest": 0.0,
        "mark_px": 0.0, "prev_day_px": 0.0, "day_ntl_vlm": 0.0, "updated_at": 0.0,
    }


def test_get_funding_uppercases_coin():
    client = TestClient(_app())
    with patch("api_server.router_orderflow.get_cached_funding", return_value=None) as mock_get:
        client.get("/orderflow/funding/btc")
    mock_get.assert_called_once_with("BTC")
