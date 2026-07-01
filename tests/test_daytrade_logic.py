"""Deterministic day-trade decision rules."""
from api_server.daytrade_logic import decide_entry, decide_exits, position_size, stop_exits


def _s(direction, signal, score, entry=100.0):
    return {"direction": direction, "signal": signal, "score": score,
            "entry": entry, "stop": entry * 0.99, "target": entry * 1.015}


def test_entry_picks_highest_conviction_long():
    scores = {
        "AAPL": _s("LONG", "BUY", 60),
        "NVDA": _s("LONG", "STRONG_BUY", 80),
        "SPY": _s("LONG", "WATCH", 45),
    }
    e = decide_entry(scores, threshold=55, allow_short=False)
    assert e["symbol"] == "NVDA"
    assert e["side"] == "buy"


def test_entry_below_threshold_none():
    scores = {"AAPL": _s("LONG", "WATCH", 45)}
    assert decide_entry(scores, threshold=55, allow_short=False) is None


def test_entry_ignores_short_when_not_allowed():
    scores = {"ETH": _s("SHORT", "STRONG_SELL", 90)}
    assert decide_entry(scores, threshold=55, allow_short=False) is None


def test_entry_allows_short_on_hl():
    scores = {"ETH": _s("SHORT", "STRONG_SELL", 90)}
    e = decide_entry(scores, threshold=55, allow_short=True)
    assert e["symbol"] == "ETH"
    assert e["side"] == "sell"


def test_entry_skips_errored_scores():
    scores = {"BTC": {"error": "boom"}, "ETH": _s("LONG", "BUY", 60)}
    e = decide_entry(scores, threshold=55, allow_short=True)
    assert e["symbol"] == "ETH"


def test_exit_on_signal_flip():
    held = [{"symbol": "ETH", "side": "long"}]
    scores = {"ETH": _s("SHORT", "STRONG_SELL", 80)}
    out = decide_exits(held, scores)
    assert len(out) == 1 and out[0]["symbol"] == "ETH"


def test_exit_on_degrade_to_avoid():
    held = [{"symbol": "BTC", "side": "short"}]
    scores = {"BTC": _s("SHORT", "AVOID", 0)}
    out = decide_exits(held, scores)
    assert out[0]["reason"].startswith("신호 소멸")


def test_no_exit_when_still_aligned():
    held = [{"symbol": "ETH", "side": "long"}]
    scores = {"ETH": _s("LONG", "STRONG_BUY", 80)}
    assert decide_exits(held, scores) == []


def test_position_size_notional():
    # equity 10000 × 10% × 3x / 2000 = 3000/2000 = 1.5
    assert position_size(10000, 0.10, 3, 2000) == 1.5


def test_position_size_zero_price():
    assert position_size(10000, 0.10, 3, 0) == 0.0


def test_stop_exits_take_profit_long():
    out = stop_exits([{"symbol": "AAPL", "side": "long", "entry": 100, "current": 116}], tp_pct=0.15, sl_pct=0.07)
    assert len(out) == 1 and out[0]["kind"] == "TAKE_PROFIT"


def test_stop_exits_stop_loss_long():
    out = stop_exits([{"symbol": "AAPL", "side": "long", "entry": 100, "current": 92}], tp_pct=0.15, sl_pct=0.07)
    assert out[0]["kind"] == "STOP_LOSS"


def test_stop_exits_short_profit_on_drop():
    out = stop_exits([{"symbol": "ETH", "side": "short", "entry": 100, "current": 80}], tp_pct=0.15, sl_pct=0.07)
    assert out[0]["kind"] == "TAKE_PROFIT"


def test_stop_exits_within_band_no_close():
    assert stop_exits([{"symbol": "X", "side": "long", "entry": 100, "current": 103}], tp_pct=0.15, sl_pct=0.07) == []


def test_stop_exits_missing_price_skipped():
    assert stop_exits([{"symbol": "X", "side": "long", "entry": 0, "current": 100}], 0.15, 0.07) == []
