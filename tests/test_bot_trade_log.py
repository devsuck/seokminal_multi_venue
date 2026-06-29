import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from live_engine.engine import LiveBotEngine, _BotRunState
from api_server.main import app, live_engine, bots

client = TestClient(app)


def _make_state(**kwargs) -> _BotRunState:
    defaults = dict(
        bot_id="b1",
        instrument_id="AAPL.NASDAQ",
        fast_ema=10,
        slow_ema=20,
        trade_size=5,
        broker=MagicMock(),
    )
    defaults.update(kwargs)
    return _BotRunState(**defaults)


def test_closed_trade_recorded_on_long_exit():
    """LONG position + SELL signal → closed trade appended."""
    state = _make_state()
    state.position = 1
    state.entry_price = 100.0
    state.entry_ts_ns = 1_000_000_000
    # Simulate SELL flip: price 110, trade_size 5
    pnl = (110.0 - 100.0) * 5
    state.closed_trades.append({
        "entry_ts_ns": state.entry_ts_ns,
        "exit_ts_ns": 2_000_000_000,
        "side": "LONG",
        "entry_price": 100.0,
        "exit_price": 110.0,
        "qty": 5,
        "pnl": round(pnl, 6),
    })
    assert len(state.closed_trades) == 1
    assert state.closed_trades[0]["side"] == "LONG"
    assert state.closed_trades[0]["pnl"] == pytest.approx(50.0)


def test_closed_trade_recorded_on_short_exit():
    """SHORT position + BUY signal → closed trade appended."""
    state = _make_state()
    state.position = -1
    state.entry_price = 100.0
    state.entry_ts_ns = 1_000_000_000
    pnl = (100.0 - 90.0) * 5
    state.closed_trades.append({
        "entry_ts_ns": state.entry_ts_ns,
        "exit_ts_ns": 2_000_000_000,
        "side": "SHORT",
        "entry_price": 100.0,
        "exit_price": 90.0,
        "qty": 5,
        "pnl": round(pnl, 6),
    })
    assert len(state.closed_trades) == 1
    assert state.closed_trades[0]["side"] == "SHORT"
    assert state.closed_trades[0]["pnl"] == pytest.approx(50.0)


def test_closed_trades_capped_at_200():
    state = _make_state()
    for i in range(205):
        state.closed_trades.append({"exit_ts_ns": i, "side": "LONG", "entry_price": 1.0,
                                     "exit_price": 1.0, "qty": 1, "pnl": 0.0, "entry_ts_ns": i})
    state.closed_trades = state.closed_trades[-200:]
    assert len(state.closed_trades) == 200


def test_signal_log_records_change():
    state = _make_state()
    state.signal_log.append({"ts_ns": 1_000_000_000, "signal": "EMA_BUY", "price": 100.0})
    assert len(state.signal_log) == 1
    assert state.signal_log[0]["signal"] == "EMA_BUY"


def test_signal_log_capped_at_100():
    state = _make_state()
    for i in range(105):
        state.signal_log.append({"ts_ns": i, "signal": "EMA_BUY", "price": float(i)})
    state.signal_log = state.signal_log[-100:]
    assert len(state.signal_log) == 100


def test_get_bot_endpoint_404():
    r = client.get("/bots/nonexistent_bot_id_xyz")
    assert r.status_code == 404


def test_get_bot_trades_endpoint_empty(monkeypatch):
    """Bot exists, not running → 200 with empty trades list."""
    monkeypatch.setitem(bots, "test_bot_1", {
        "id": "test_bot_1", "name": "TestBot", "strategy": "ema_cross",
        "instrument_id": "AAPL.NASDAQ", "fast_ema": 10, "slow_ema": 20,
        "trade_size": 5, "status": "stopped", "created_at": "2026-01-01T00:00:00Z",
    })
    monkeypatch.setattr(live_engine, "_running", {})
    r = client.get("/bots/test_bot_1/trades")
    assert r.status_code == 200
    data = r.json()
    assert data["bot_id"] == "test_bot_1"
    assert data["trades"] == []


def test_get_bot_signals_endpoint_with_data(monkeypatch):
    """Bot running with signal_log → signals returned."""
    monkeypatch.setitem(bots, "test_bot_2", {
        "id": "test_bot_2", "name": "TestBot2", "strategy": "ema_cross",
        "instrument_id": "AAPL.NASDAQ", "fast_ema": 10, "slow_ema": 20,
        "trade_size": 5, "status": "running", "created_at": "2026-01-01T00:00:00Z",
    })
    state = _make_state(bot_id="test_bot_2")
    state.signal_log = [{"ts_ns": 1_000_000_000, "signal": "EMA_BUY", "price": 150.0}]
    monkeypatch.setattr(live_engine, "_running", {"test_bot_2": state})
    r = client.get("/bots/test_bot_2/signals")
    assert r.status_code == 200
    data = r.json()
    assert len(data["signals"]) == 1
    assert data["signals"][0]["signal"] == "EMA_BUY"
