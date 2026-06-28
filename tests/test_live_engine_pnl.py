import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from live_engine.engine import LiveBotEngine, _BotRunState
from api_server.main import app, _compute_unrealized_pnl

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


def test_get_status_entry_price_none_by_default():
    eng = LiveBotEngine()
    state = _make_state()
    eng._running["b1"] = state
    status = eng.get_status("b1")
    assert status.entry_price is None


def test_get_status_returns_entry_price_when_set():
    eng = LiveBotEngine()
    state = _make_state()
    state.entry_price = 150.0
    state.position = 1
    state.last_price = 155.0
    eng._running["b1"] = state
    status = eng.get_status("b1")
    assert status.entry_price == 150.0


def test_compute_unrealized_pnl_long():
    # entry=100, last=110, qty=5, LONG → (110-100)*5*1 = 50
    pnl = _compute_unrealized_pnl("LONG", 5.0, 110.0, 100.0)
    assert pnl == pytest.approx(50.0)


def test_compute_unrealized_pnl_short():
    # entry=100, last=90, qty=5, SHORT → (90-100)*5*(-1) = 50
    pnl = _compute_unrealized_pnl("SHORT", 5.0, 90.0, 100.0)
    assert pnl == pytest.approx(50.0)


def test_compute_unrealized_pnl_flat_returns_none():
    assert _compute_unrealized_pnl("FLAT", 0.0, 100.0, 100.0) is None


def test_compute_unrealized_pnl_missing_entry_returns_none():
    assert _compute_unrealized_pnl("LONG", 5.0, 110.0, None) is None


def test_compute_unrealized_pnl_missing_last_returns_none():
    assert _compute_unrealized_pnl("LONG", 5.0, None, 100.0) is None
