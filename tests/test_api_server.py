import pytest
from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app)


def test_bars_happy_path_returns_known_instrument_data():
    response = client.get(
        "/bars",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["instrument_id"] == "AAPL.NASDAQ"
    assert len(body["bars"]) > 0
    first_bar = body["bars"][0]
    assert set(first_bar.keys()) == {
        "ts_event",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }


def test_bars_unknown_instrument_returns_400():
    response = client.get(
        "/bars",
        params={
            "instrument_id": "NOPE.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 400


def test_backtest_happy_path_returns_all_metric_keys():
    response = client.get(
        "/backtest",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
            "strategy": "ema_cross",
            "fast": 10,
            "slow": 20,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "sharpe_ratio",
        "max_drawdown",
        "total_pnl",
        "total_pnl_pct",
        "bar_count",
    }


def test_backtest_unsupported_strategy_returns_400():
    response = client.get(
        "/backtest",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
            "strategy": "not_a_real_strategy",
            "fast": 10,
            "slow": 20,
        },
    )
    assert response.status_code == 400


def test_correlation_happy_path_returns_known_pair_value():
    response = client.get(
        "/correlation",
        params={
            "instrument_ids": "005930.XKRX,000660.XKRX",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 200
    body = response.json()
    pairs = {(p["a"], p["b"]): p["correlation"] for p in body["pairs"]}
    assert 0.5 < pairs[("005930.XKRX", "000660.XKRX")] < 0.9


def test_correlation_single_instrument_returns_400():
    response = client.get(
        "/correlation",
        params={
            "instrument_ids": "005930.XKRX",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 400
