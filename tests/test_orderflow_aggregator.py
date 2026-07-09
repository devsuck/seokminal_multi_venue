from orderflow.aggregator import OrderflowAggregator
from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent


def _trade(price, size, side, ts):
    return TradeEvent(symbol="BTC.HL", ts=ts, price=price, size=size, side=side)


def test_on_trade_accumulates_buy_and_sell_volume_in_same_bucket():
    agg = OrderflowAggregator(tick_size=1.0, footprint_bucket_sec=60.0)
    d1 = agg.on_trade(_trade(65000.4, 1.0, "buy", ts=1000.0))
    d2 = agg.on_trade(_trade(65000.6, 0.5, "sell", ts=1010.0))
    assert d1 == {"type": "footprint_delta", "bucket_ts": 960.0, "price": 65000.0, "side": "buy", "delta_vol": 1.0}
    assert d2["side"] == "sell"
    assert d2["bucket_ts"] == 960.0

    snap = agg.snapshot()
    cell = next(c for c in snap["footprint"] if c["price"] == 65000.0)
    assert cell["buy_vol"] == 1.0
    assert cell["sell_vol"] == 0.5


def test_on_trade_separates_buckets_by_time():
    agg = OrderflowAggregator(tick_size=1.0, footprint_bucket_sec=60.0)
    agg.on_trade(_trade(100.0, 1.0, "buy", ts=0.0))
    agg.on_trade(_trade(100.0, 1.0, "buy", ts=120.0))
    snap = agg.snapshot()
    bucket_ts_set = {c["bucket_ts"] for c in snap["footprint"]}
    assert bucket_ts_set == {0.0, 120.0}


def test_on_book_snapshot_creates_heatmap_cells_for_each_level():
    agg = OrderflowAggregator(tick_size=1.0, heatmap_bucket_sec=2.0)
    book = OrderBookSnapshot(
        symbol="BTC.HL", ts=10.0,
        bids=[OrderBookLevel(price=99.4, size=5.0)],
        asks=[OrderBookLevel(price=101.4, size=3.0)],
    )
    deltas = agg.on_book_snapshot(book)
    assert {"type": "heatmap_delta", "ts": 10.0, "price": 99.0, "size": 5.0} in deltas
    assert {"type": "heatmap_delta", "ts": 10.0, "price": 101.0, "size": 3.0} in deltas
    snap = agg.snapshot()
    assert len(snap["heatmap"]) == 2


def test_prunes_footprint_buckets_older_than_max_window():
    agg = OrderflowAggregator(tick_size=1.0, footprint_bucket_sec=60.0, max_window_sec=120.0)
    agg.on_trade(_trade(100.0, 1.0, "buy", ts=0.0))
    agg.on_trade(_trade(100.0, 1.0, "buy", ts=300.0))  # 최신 버킷 기준 120s 밖 -> 첫 버킷 정리
    snap = agg.snapshot()
    bucket_ts_set = {c["bucket_ts"] for c in snap["footprint"]}
    assert 0.0 not in bucket_ts_set
    assert 300.0 in bucket_ts_set


def test_round_price_guards_against_float_division_noise():
    """Regression test for float precision bug in _round_price with fractional tick sizes.

    Without epsilon guard, 0.3 / 0.1 = 2.9999999999999996 in Python, causing floor() to
    incorrectly bucket price 0.3 at 0.2 instead of 0.3.
    """
    agg = OrderflowAggregator(tick_size=0.1, footprint_bucket_sec=60.0)
    d = agg.on_trade(_trade(price=0.3, size=1.0, side="buy", ts=1000.0))
    assert d["price"] == 0.3, f"Expected price 0.3 but got {d['price']}"
    snap = agg.snapshot()
    prices = {c["price"] for c in snap["footprint"]}
    assert 0.3 in prices, f"Price 0.3 not found in footprint. Got prices: {prices}"
