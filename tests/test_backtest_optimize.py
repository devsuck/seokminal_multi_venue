import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from api_server.main import app

client = TestClient(app)


def _fake_simple_backtest(bars, strategy, params):
    sharpe = sum(p for p in params.values() if isinstance(p, (int, float))) / 100.0
    return {
        "bar_count": len(bars), "sharpe_ratio": sharpe, "sortino_ratio": None,
        "max_drawdown": None, "volatility": None, "total_pnl": 0.0,
        "total_pnl_pct": 0.0, "win_rate": None, "profit_loss_ratio": None,
        "avg_win": None, "avg_loss": None, "trades": [],
    }


def _fake_bars(n=50):
    bar = MagicMock()
    bar.close = 100.0
    bar.ts_event = 1_704_067_200_000_000_000  # 2024-01-01 00:00:00 UTC in nanoseconds
    return [bar] * n


def test_backtest_optimize_macd_returns_best_params():
    with (
        patch("api_server.main.ParquetDataCatalog") as mock_cat,
        patch("api_server.main.run_simple_backtest", side_effect=_fake_simple_backtest),
        patch("api_server.main.bar_type_for") as mock_bt,
        patch("api_server.main.InstrumentId") as mock_iid,
    ):
        mock_cat.return_value.bars.return_value = _fake_bars()
        mock_bt.return_value = MagicMock(__str__=lambda s: "bar_type")
        mock_iid.from_str.return_value = MagicMock()

        r = client.get("/backtest/optimize?instrument_id=AAPL.NASDAQ&start=2024-01-01&end=2024-12-31&strategy=macd")
    assert r.status_code == 200
    data = r.json()
    assert "best_params" in data
    assert "best_sharpe" in data
    assert data["combinations_tested"] > 0


def test_backtest_optimize_rsi_returns_best_params():
    with (
        patch("api_server.main.ParquetDataCatalog") as mock_cat,
        patch("api_server.main.run_simple_backtest", side_effect=_fake_simple_backtest),
        patch("api_server.main.bar_type_for") as mock_bt,
        patch("api_server.main.InstrumentId") as mock_iid,
    ):
        mock_cat.return_value.bars.return_value = _fake_bars()
        mock_bt.return_value = MagicMock(__str__=lambda s: "bar_type")
        mock_iid.from_str.return_value = MagicMock()

        r = client.get("/backtest/optimize?instrument_id=AAPL.NASDAQ&start=2024-01-01&end=2024-12-31&strategy=rsi")
    assert r.status_code == 200
    data = r.json()
    assert "best_params" in data
    assert data["combinations_tested"] > 0


def test_backtest_optimize_invalid_strategy_returns_400():
    r = client.get("/backtest/optimize?instrument_id=AAPL.NASDAQ&start=2024-01-01&end=2024-12-31&strategy=ema_cross")
    assert r.status_code == 400


def test_backtest_macd_strategy_returns_200():
    with (
        patch("api_server.main.ParquetDataCatalog") as mock_cat,
        patch("api_server.main.run_simple_backtest") as mock_run,
        patch("api_server.main.bar_type_for") as mock_bt,
        patch("api_server.main.InstrumentId") as mock_iid,
    ):
        mock_cat.return_value.bars.return_value = _fake_bars()
        mock_run.return_value = {
            "bar_count": 50, "sharpe_ratio": 0.5, "sortino_ratio": None,
            "max_drawdown": -0.1, "volatility": 0.2, "total_pnl": 100.0,
            "total_pnl_pct": 0.1, "win_rate": 0.6, "profit_loss_ratio": 1.5,
            "avg_win": 20.0, "avg_loss": -10.0, "trades": [],
        }
        mock_bt.return_value = MagicMock(__str__=lambda s: "bar_type")
        mock_iid.from_str.return_value = MagicMock()

        r = client.get("/backtest?instrument_id=AAPL.NASDAQ&start=2024-01-01&end=2024-12-31&strategy=macd&fast=12&slow=26&signal_period=9")
    assert r.status_code == 200
    data = r.json()
    assert "sharpe_ratio" in data
