from orderflow.models import (
    FootprintCell,
    HeatmapCell,
    OrderBookLevel,
    OrderBookSnapshot,
    TradeEvent,
)


def test_order_book_snapshot_round_trip():
    snap = OrderBookSnapshot(
        symbol="BTC.HL",
        ts=1720000000.0,
        bids=[OrderBookLevel(price=65000.0, size=1.5)],
        asks=[OrderBookLevel(price=65010.0, size=2.0)],
    )
    assert snap.bids[0].price == 65000.0
    assert snap.asks[0].size == 2.0


def test_trade_event_side_must_be_buy_or_sell():
    trade = TradeEvent(symbol="NQ", ts=1720000000.0, price=101.0, size=2.0, side="buy")
    assert trade.side == "buy"
    try:
        TradeEvent(symbol="NQ", ts=1720000000.0, price=101.0, size=2.0, side="hold")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for invalid side")


def test_footprint_and_heatmap_cells_construct():
    fp = FootprintCell(bucket_ts=1720000000.0, price=65000.0, buy_vol=1.0, sell_vol=0.5)
    hm = HeatmapCell(ts=1720000000.0, price=65000.0, size=3.4)
    assert fp.buy_vol == 1.0
    assert hm.size == 3.4
