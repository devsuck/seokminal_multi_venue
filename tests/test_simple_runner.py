import pytest
from backtest_runner.simple_runner import (
    _ema_series,
    _macd_signals,
    _rsi_series,
    _rsi_signals,
    _simulate_trades,
    run_simple_backtest,
)


class _FakeBar:
    def __init__(self, close: float, ts_event: int):
        self.close = close
        self.ts_event = ts_event


def test_ema_series_warmup_is_none():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    emas = _ema_series(vals, period=3)
    assert emas[0] is None
    assert emas[1] is None
    assert emas[2] == pytest.approx(2.0)  # (1+2+3)/3


def test_ema_series_too_short_returns_all_none():
    emas = _ema_series([1.0, 2.0], period=5)
    assert all(v is None for v in emas)


def test_macd_signals_length_matches_input():
    closes = [float(i) for i in range(50)]
    sigs = _macd_signals(closes, fast=5, slow=10, signal_period=3)
    assert len(sigs) == 50


def test_macd_signals_only_valid_values():
    closes = [float(i) for i in range(50)]
    sigs = _macd_signals(closes, fast=5, slow=10, signal_period=3)
    assert all(s in {"BUY", "SELL", "HOLD"} for s in sigs)


def test_rsi_series_range():
    """RSI values must be in [0, 100]."""
    closes = [100 + ((-1) ** i) * (i % 5) for i in range(30)]
    rsi = _rsi_series(closes, period=14)
    for v in rsi:
        if v is not None:
            assert 0 <= v <= 100


def test_rsi_signals_buy_on_oversold_cross():
    """Force RSI to rise above 30 — expect BUY signal."""
    # Create a sequence: declining prices (pushes RSI low), then strong recovery
    closes = [100 - i * 2 for i in range(20)] + [70 + i * 5 for i in range(10)]
    signals = _rsi_signals(closes, period=14, oversold=30, overbought=70)
    assert any(s == "BUY" for s in signals)


def test_simulate_trades_long_exit_pnl():
    closes = [100.0, 100.0, 110.0]
    ts = [1_000_000, 2_000_000, 3_000_000]
    signals = ["BUY", "HOLD", "SELL"]
    trades = _simulate_trades(closes, ts, signals, trade_size=5)
    # BUY at 100, SELL at 110 → PnL = (110-100)*5 = 50
    assert len(trades) == 1
    assert trades[0]["pnl"] == pytest.approx(50.0)
    assert trades[0]["side"] == "LONG"


def test_simulate_trades_open_position_closed_at_last_bar():
    closes = [100.0, 105.0]
    ts = [1_000_000, 2_000_000]
    signals = ["BUY", "HOLD"]
    trades = _simulate_trades(closes, ts, signals, trade_size=10)
    # BUY at 100, auto-closed at 105 → PnL = (105-100)*10 = 50
    assert len(trades) == 1
    assert trades[0]["exit_price"] == 105.0


def test_run_simple_backtest_macd_returns_dict():
    bars = [_FakeBar(100 + i % 10, i * 1_000_000) for i in range(60)]
    result = run_simple_backtest(bars, "macd", {"fast": 5, "slow": 10, "signal_period": 3, "trade_size": 5})
    assert "sharpe_ratio" in result
    assert "trades" in result
    assert result["bar_count"] == 60


def test_run_simple_backtest_rsi_returns_dict():
    bars = [_FakeBar(100 + ((-1) ** i) * (i % 8), i * 1_000_000) for i in range(60)]
    result = run_simple_backtest(bars, "rsi", {"period": 14, "oversold": 30, "overbought": 70, "trade_size": 5})
    assert "sharpe_ratio" in result
    assert result["bar_count"] == 60
