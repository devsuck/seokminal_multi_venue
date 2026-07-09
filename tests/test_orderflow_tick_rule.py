from orderflow.tick_rule import classify


def test_price_at_or_above_ask_is_buy():
    assert classify(price=101.0, bid=100.0, ask=101.0) == "buy"
    assert classify(price=102.0, bid=100.0, ask=101.0) == "buy"


def test_price_at_or_below_bid_is_sell():
    assert classify(price=100.0, bid=100.0, ask=101.0) == "sell"
    assert classify(price=99.0, bid=100.0, ask=101.0) == "sell"


def test_price_between_bid_and_ask_uses_mid():
    # bid=100, ask=102 -> mid=101
    assert classify(price=101.0, bid=100.0, ask=102.0) == "buy"   # >= mid
    assert classify(price=100.5, bid=100.0, ask=102.0) == "sell"  # < mid
