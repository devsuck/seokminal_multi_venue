"""Walk-forward backtest endpoint tests."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app)


def _make_mock_bars(n: int = 100, trend: float = 0.3) -> list:
    bars = []
    price = 100.0
    for i in range(n):
        price += trend + (i % 5) * 0.05
        b = MagicMock()
        b.close = price
        b.open = price - 0.1
        b.high = price + 0.2
        b.low = price - 0.2
        b.volume = 1000
        b.ts_event = (1700000000 + i * 86400) * 10**9
        bars.append(b)
    return bars


def test_walk_forward_macd_basic():
    with patch("api_server.main.ParquetDataCatalog") as MockCat:
        MockCat.return_value.bars.return_value = _make_mock_bars(100)
        r = client.get(
            "/backtest/walk-forward",
            params={
                "instrument_id": "AAPL.NASDAQ",
                "start": "2023-01-01",
                "end": "2024-01-01",
                "strategy": "macd",
                "n_windows": 4,
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data["n_windows"] == 4
    assert data["strategy"] == "macd"
    assert len(data["windows"]) > 0
    assert "summary" in data
    assert "avg_sharpe" in data["summary"]
    assert "profitable_windows" in data["summary"]
    assert data["summary"]["total_windows"] == len(data["windows"])


def test_walk_forward_rsi():
    with patch("api_server.main.ParquetDataCatalog") as MockCat:
        MockCat.return_value.bars.return_value = _make_mock_bars(80)
        r = client.get(
            "/backtest/walk-forward",
            params={
                "instrument_id": "AAPL.NASDAQ",
                "start": "2023-01-01",
                "end": "2024-01-01",
                "strategy": "rsi",
                "n_windows": 3,
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert len(data["windows"]) == 3


def test_walk_forward_xgb():
    with patch("api_server.main.ParquetDataCatalog") as MockCat:
        MockCat.return_value.bars.return_value = _make_mock_bars(150)
        r = client.get(
            "/backtest/walk-forward",
            params={
                "instrument_id": "AAPL.NASDAQ",
                "start": "2023-01-01",
                "end": "2024-06-01",
                "strategy": "xgb",
                "n_windows": 3,
                "xgb_n_estimators": 10,
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert len(data["windows"]) == 3
    for w in data["windows"]:
        assert "window_start" in w
        assert "window_end" in w
        assert "num_trades" in w


def test_walk_forward_ema_cross():
    with patch("api_server.main.ParquetDataCatalog") as MockCat:
        MockCat.return_value.bars.return_value = _make_mock_bars(120)
        r = client.get(
            "/backtest/walk-forward",
            params={
                "instrument_id": "AAPL.NASDAQ",
                "start": "2023-01-01",
                "end": "2024-01-01",
                "strategy": "ema_cross",
                "n_windows": 5,
                "fast": 10,
                "slow": 20,
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert len(data["windows"]) == 5


def test_walk_forward_invalid_strategy():
    r = client.get(
        "/backtest/walk-forward",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2023-01-01",
            "end": "2024-01-01",
            "strategy": "unknown_strategy",
            "n_windows": 3,
        },
    )
    assert r.status_code == 400


def test_walk_forward_insufficient_bars():
    with patch("api_server.main.ParquetDataCatalog") as MockCat:
        MockCat.return_value.bars.return_value = _make_mock_bars(5)
        r = client.get(
            "/backtest/walk-forward",
            params={
                "instrument_id": "AAPL.NASDAQ",
                "start": "2023-01-01",
                "end": "2024-01-01",
                "strategy": "macd",
                "n_windows": 5,
            },
        )
    assert r.status_code == 400
