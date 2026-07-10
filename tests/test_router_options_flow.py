import asyncio
from unittest.mock import patch

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from api_server.router_options_flow import router


class _StubManager:
    def __init__(self, subscribe_result=None):
        self._subscribe_result = subscribe_result
        self.unsubscribed: list[tuple[str, object]] = []

    def subscribe(self, currency):
        return self._subscribe_result

    def unsubscribe(self, currency, queue):
        self.unsubscribed.append((currency, queue))


def _app():
    app = FastAPI()
    app.include_router(router)
    return app


def test_get_gex_returns_cached_snapshot():
    cached = {"currency": "BTC", "spot": 95000.0, "updated_at": 1000.0, "levels": []}
    client = TestClient(_app())
    with patch("api_server.router_options_flow.get_cached_gex", return_value=cached):
        r = client.get("/options-flow/gex/BTC")
    assert r.status_code == 200
    assert r.json() == cached


def test_get_gex_returns_empty_snapshot_when_not_cached_yet():
    client = TestClient(_app())
    with patch("api_server.router_options_flow.get_cached_gex", return_value=None):
        r = client.get("/options-flow/gex/BTC")
    assert r.json() == {"currency": "BTC", "spot": 0.0, "updated_at": 0.0, "levels": []}


def test_get_gex_unsupported_currency_returns_empty_without_lookup():
    client = TestClient(_app())
    with patch("api_server.router_options_flow.get_cached_gex") as mock_get:
        r = client.get("/options-flow/gex/DOGE")
    mock_get.assert_not_called()
    assert r.json() == {"currency": "DOGE", "spot": 0.0, "updated_at": 0.0, "levels": []}


def test_ws_options_flow_streams_queued_trade_then_cleans_up_on_disconnect():
    queue = asyncio.Queue()
    queue.put_nowait({"type": "trade", "instrument_name": "BTC-27DEC26-100000-C"})
    stub = _StubManager(subscribe_result=queue)
    client = TestClient(_app())

    with patch("api_server.router_options_flow.default_manager", stub):
        with client.websocket_connect("/ws/options-flow/BTC") as ws:
            msg = ws.receive_json()

    assert msg["type"] == "trade"
    assert stub.unsubscribed == [("BTC", queue)]


def test_ws_options_flow_unsupported_currency_closes_after_accept():
    client = TestClient(_app())
    with client.websocket_connect("/ws/options-flow/DOGE") as ws:
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
