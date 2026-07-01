"""Order-sizing correctness for the bot engine (stop-and-reverse position model).

Regression guard for the position-desync bug: a reversal must trade enough to
both close the old position and open the new one, so the engine's tracked
position always matches what it actually sent to the broker.
"""
from live_engine.engine import _order_for_target, _target_units


def test_target_units_long_when_fast_above_slow():
    assert _target_units(fast=11.0, slow=10.0, current=0) == 1


def test_target_units_short_when_fast_below_slow():
    assert _target_units(fast=9.0, slow=10.0, current=0) == -1


def test_target_units_holds_current_when_equal():
    assert _target_units(fast=10.0, slow=10.0, current=1) == 1
    assert _target_units(fast=10.0, slow=10.0, current=-1) == -1


def test_no_order_when_already_at_target():
    assert _order_for_target(current_units=1, target_units=1, trade_size=5) is None
    assert _order_for_target(current_units=0, target_units=0, trade_size=5) is None


def test_flat_to_long_buys_one_unit():
    # 0 -> +1 : BUY trade_size
    assert _order_for_target(current_units=0, target_units=1, trade_size=5) == ("BUY", 5)


def test_flat_to_short_sells_one_unit():
    assert _order_for_target(current_units=0, target_units=-1, trade_size=5) == ("SELL", 5)


def test_long_to_short_sells_two_units():
    # +1 -> -1 : SELL 2*trade_size (close long + open short) — the bug fix
    assert _order_for_target(current_units=1, target_units=-1, trade_size=5) == ("SELL", 10)


def test_short_to_long_buys_two_units():
    # -1 -> +1 : BUY 2*trade_size (cover short + open long)
    assert _order_for_target(current_units=-1, target_units=1, trade_size=5) == ("BUY", 10)


def test_long_to_flat_sells_one_unit():
    assert _order_for_target(current_units=1, target_units=0, trade_size=5) == ("SELL", 5)
