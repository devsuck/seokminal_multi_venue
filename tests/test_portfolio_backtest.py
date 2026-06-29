import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backtest_runner.simple_runner import _ema_signals, run_simple_backtest
from api_server.main import app

client = TestClient(app)


def _fake_report(bars, strategy, params):
    return {
        "bar_count": len(bars),
        "sharpe_ratio": 1.0, "sortino_ratio": None, "max_drawdown": -0.1,
        "volatility": 0.2, "total_pnl": 100.0, "total_pnl_pct": 0.05,
        "win_rate": 0.6, "profit_loss_ratio": 1.5, "avg_win": 100.0, "avg_loss": -50.0,
        "trades": [
            {
                "entry_ts_ns": 1_704_067_200_000_000_000,
                "exit_ts_ns": 1_704_153_600_000_000_000,
                "side": "LONG", "entry_price": 100.0, "exit_price": 110.0,
                "qty": 10, "pnl": 100.0,
            }
        ],
    }


def _fake_bars(n=50):
    bar = MagicMock()
    bar.close = 100.0
    bar.ts_event = 1_704_067_200_000_000_000  # 2024-01-01 UTC in nanoseconds
    return [bar] * n


def test_ema_signals_constant_closes_all_hold():
    closes = [100.0] * 30
    signals = _ema_signals(closes, fast=5, slow=10)
    assert len(signals) == 30
    assert set(signals) == {"HOLD"}


def test_ema_signals_golden_cross():
    # Sharp price jump: fast EMA will cross above slow EMA
    closes = [100.0] * 30 + [200.0] * 30
    signals = _ema_signals(closes, fast=12, slow=26)
    assert "BUY" in signals
    assert "SELL" not in signals


def test_ema_signals_death_cross():
    # Sharp price drop: fast EMA will cross below slow EMA
    closes = [200.0] * 30 + [100.0] * 30
    signals = _ema_signals(closes, fast=12, slow=26)
    assert "SELL" in signals


def test_run_simple_backtest_ema_cross_returns_all_keys():
    bars = _fake_bars(50)
    report = run_simple_backtest(bars, "ema_cross", {"fast": 5, "slow": 10})
    for key in [
        "sharpe_ratio", "sortino_ratio", "max_drawdown", "volatility",
        "total_pnl", "total_pnl_pct", "win_rate", "profit_loss_ratio",
        "avg_win", "avg_loss", "bar_count", "trades",
    ]:
        assert key in report


def test_portfolio_backtest_equity_starts_at_zero_and_grows():
    with (
        patch("api_server.main.ParquetDataCatalog") as mock_cat,
        patch("api_server.main.run_simple_backtest", side_effect=_fake_report),
        patch("api_server.main.bar_type_for") as mock_bt,
        patch("api_server.main.InstrumentId") as mock_iid,
    ):
        mock_cat.return_value.bars.return_value = _fake_bars(1)
        mock_bt.return_value = MagicMock(__str__=lambda s: "bar_type")
        mock_iid.from_str.return_value = MagicMock()

        r = client.get(
            "/backtest/portfolio"
            "?instrument_ids=AAPL.NASDAQ,SPY.ARCA"
            "&start=2024-01-01&end=2024-12-31&strategy=macd"
        )

    assert r.status_code == 200
    data = r.json()
    assert data["portfolio_equity"][0]["equity"] == 0.0
    assert data["portfolio_equity"][-1]["equity"] > 0.0
    assert data["portfolio_total_pnl"] > 0.0
    assert len(data["results"]) == 2
    assert data["results"][0]["instrument_id"] in {"AAPL.NASDAQ", "SPY.ARCA"}
