import asyncio
import gzip
import json
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_server.router_orderflow as router_orderflow
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


def test_get_history_dates_returns_empty_for_non_hl_symbol():
    client = TestClient(_app())
    r = client.get("/orderflow/history/NQ/dates")
    assert r.json() == {"symbol": "NQ", "dates": []}


def test_get_history_dates_lists_dates_for_coin_only(tmp_path):
    (tmp_path / "BTC_2026-07-28.jsonl").write_text("")
    (tmp_path / "BTC_2026-07-29.jsonl.gz").write_text("")
    (tmp_path / "ETH_2026-07-29.jsonl").write_text("")  # 다른 코인은 제외
    (tmp_path / "not_a_snapshot_file.txt").write_text("")
    client = TestClient(_app())
    with patch.object(router_orderflow, "_SNAPSHOT_DATA_DIR", tmp_path):
        r = client.get("/orderflow/history/BTC.HL/dates")
    assert r.json() == {"symbol": "BTC.HL", "dates": ["2026-07-28", "2026-07-29"]}


def test_get_history_dates_when_dir_missing(tmp_path):
    client = TestClient(_app())
    with patch.object(router_orderflow, "_SNAPSHOT_DATA_DIR", tmp_path / "missing"):
        r = client.get("/orderflow/history/BTC.HL/dates")
    assert r.json() == {"symbol": "BTC.HL", "dates": []}


def test_get_history_404_for_non_hl_symbol():
    client = TestClient(_app())
    r = client.get("/orderflow/history/NQ", params={"date": "2026-07-29"})
    assert r.status_code == 404


def test_get_history_returns_empty_when_no_file(tmp_path):
    client = TestClient(_app())
    with patch.object(router_orderflow, "_SNAPSHOT_DATA_DIR", tmp_path):
        r = client.get("/orderflow/history/BTC.HL", params={"date": "2026-07-29"})
    assert r.json() == {"symbol": "BTC.HL", "date": "2026-07-29", "snapshots": [], "truncated": False}


def test_get_history_reads_plain_jsonl_and_filters_by_range(tmp_path):
    path = tmp_path / "BTC_2026-07-29.jsonl"
    rows = [{"ts": t, "bids": [], "asks": []} for t in (1.0, 5.0, 10.0)]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    client = TestClient(_app())
    with patch.object(router_orderflow, "_SNAPSHOT_DATA_DIR", tmp_path):
        r = client.get("/orderflow/history/BTC.HL", params={"date": "2026-07-29", "start": 2.0, "end": 9.0})
    body = r.json()
    assert [s["ts"] for s in body["snapshots"]] == [5.0]
    assert body["truncated"] is False


def test_get_history_reads_gzip_when_plain_missing(tmp_path):
    path = tmp_path / "BTC_2026-07-29.jsonl.gz"
    row = {"ts": 1.0, "bids": [[100.0, 1.0]], "asks": []}
    with gzip.open(path, "wt") as f:
        f.write(json.dumps(row) + "\n")
    client = TestClient(_app())
    with patch.object(router_orderflow, "_SNAPSHOT_DATA_DIR", tmp_path):
        r = client.get("/orderflow/history/BTC.HL", params={"date": "2026-07-29"})
    assert r.json()["snapshots"] == [row]


def test_get_history_prefers_plain_over_gzip_when_both_exist(tmp_path):
    plain_row = {"ts": 1.0, "bids": [], "asks": []}
    (tmp_path / "BTC_2026-07-29.jsonl").write_text(json.dumps(plain_row) + "\n")
    with gzip.open(tmp_path / "BTC_2026-07-29.jsonl.gz", "wt") as f:
        f.write(json.dumps({"ts": 999.0, "bids": [], "asks": []}) + "\n")
    client = TestClient(_app())
    with patch.object(router_orderflow, "_SNAPSHOT_DATA_DIR", tmp_path):
        r = client.get("/orderflow/history/BTC.HL", params={"date": "2026-07-29"})
    assert r.json()["snapshots"] == [plain_row]


def test_get_history_truncates_at_limit(tmp_path):
    path = tmp_path / "BTC_2026-07-29.jsonl"
    rows = [{"ts": float(t), "bids": [], "asks": []} for t in range(5)]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    client = TestClient(_app())
    with patch.object(router_orderflow, "_SNAPSHOT_DATA_DIR", tmp_path):
        r = client.get("/orderflow/history/BTC.HL", params={"date": "2026-07-29", "limit": 2})
    body = r.json()
    assert len(body["snapshots"]) == 2
    assert body["truncated"] is True
