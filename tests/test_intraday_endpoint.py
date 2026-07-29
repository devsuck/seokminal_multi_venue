"""Intraday scoring endpoint wiring (bars fetch monkeypatched)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api_server.routers import alpaca_shared as shared
from api_server.main import app

client = TestClient(app)


def _synth_long_bars():
    closes = [100, 100.2, 99.8, 100.1, 100.3, 100.0, 101.5, 102.2, 103.0, 102.6, 103.4, 104.0]
    vols = [1000, 1100, 900, 1000, 1050, 1000, 2500, 3000, 3500, 3200, 4000, 4500]
    t0 = datetime(2026, 6, 30, 14, 0, tzinfo=timezone.utc)  # 10:00 ET
    bars, prev = [], closes[0]
    for i, c in enumerate(closes):
        bars.append({"t": t0 + timedelta(minutes=5 * i), "o": prev,
                     "h": max(prev, c) + 0.5, "l": min(prev, c) - 0.5, "c": c, "v": vols[i]})
        prev = c
    return bars


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setattr(shared, "ALPACA_KEY", "test-key")


def test_intraday_score_endpoint(monkeypatch):
    monkeypatch.setattr(shared, "_fetch_intraday_bars", lambda symbol, days=2: _synth_long_bars())
    r = client.get("/alpaca/intraday/score/AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["direction"] == "LONG"
    assert body["signal"] in ("BUY", "STRONG_BUY")
    assert "entry" in body and "stop" in body and "target" in body


def test_intraday_scores_batch(monkeypatch):
    monkeypatch.setattr(shared, "_fetch_intraday_bars", lambda symbol, days=2: _synth_long_bars())
    r = client.get("/alpaca/intraday/scores?symbols=AAPL,NVDA")
    assert r.status_code == 200
    scores = r.json()["scores"]
    assert set(scores.keys()) == {"AAPL", "NVDA"}
    assert scores["AAPL"]["direction"] == "LONG"
