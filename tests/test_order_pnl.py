from api_server.order_pnl import compute_realized_pnl, price_fallback_from_audit


def _order(venue, order_id, symbol, side, filled, price, ts="t1"):
    return {
        "venue": venue, "order_id": order_id, "symbol": symbol, "side": side,
        "filled": filled, "remaining": 0.0, "price": price,
        "created_ts": ts, "updated_ts": ts, "status": "FILLED", "history": [],
    }


def test_no_orders_is_empty():
    assert compute_realized_pnl([]) == []


def test_unfilled_orders_are_excluded():
    orders = [_order("US", "1", "AAPL", "buy", 0.0, 100.0)]
    assert compute_realized_pnl(orders) == []


def test_buy_then_sell_realizes_pnl_with_broker_price():
    orders = [
        _order("US", "1", "AAPL", "buy", 10, 100.0, ts="t1"),
        _order("US", "2", "AAPL", "sell", 10, 110.0, ts="t2"),
    ]
    [venue_pnl] = compute_realized_pnl(orders)
    assert venue_pnl.venue == "US"
    assert venue_pnl.gross_realized_pnl == 100.0  # (110-100)*10
    assert venue_pnl.net_realized_pnl == 100.0  # no fee configured
    assert venue_pnl.open_positions == []
    assert venue_pnl.trades[0]["price_source"] == "broker"
    assert venue_pnl.trades[1]["realized_pnl"] == 100.0


def test_partial_sell_keeps_open_position():
    orders = [
        _order("US", "1", "AAPL", "buy", 10, 100.0, ts="t1"),
        _order("US", "2", "AAPL", "sell", 4, 120.0, ts="t2"),
    ]
    [venue_pnl] = compute_realized_pnl(orders)
    assert venue_pnl.gross_realized_pnl == 80.0  # (120-100)*4
    assert venue_pnl.open_positions == [{"symbol": "AAPL", "qty": 6, "avg_price": 100.0}]


def test_kr_order_falls_back_to_requested_price_when_no_broker_price():
    orders = [_order("KR", "1", "005930", "buy", 10, None, ts="t1")]
    fallback = {("KR", "1"): 70000.0}
    [venue_pnl] = compute_realized_pnl(orders, fallback)
    assert venue_pnl.trades[0]["price"] == 70000.0
    assert venue_pnl.trades[0]["price_source"] == "estimated"


def test_order_with_no_price_anywhere_is_excluded_but_counted():
    orders = [_order("KR", "1", "005930", "buy", 10, None, ts="t1")]
    [venue_pnl] = compute_realized_pnl(orders, price_fallback=None)
    assert venue_pnl.trades == []
    assert venue_pnl.unpriced_fills == 1


def test_fee_bps_reduces_net_pnl(monkeypatch):
    monkeypatch.setenv("PNL_FEE_BPS_US", "10")  # 0.1% per leg
    orders = [
        _order("US", "1", "AAPL", "buy", 10, 100.0, ts="t1"),
        _order("US", "2", "AAPL", "sell", 10, 110.0, ts="t2"),
    ]
    [venue_pnl] = compute_realized_pnl(orders)
    # fee = (100*10 + 110*10) * 10bps/10000 = 2100 * 0.001 = 2.1
    assert venue_pnl.fees == 2.1
    assert venue_pnl.net_realized_pnl == 97.9


def test_venues_are_kept_separate():
    orders = [
        _order("US", "1", "AAPL", "buy", 10, 100.0, ts="t1"),
        _order("KR", "1", "005930", "buy", 5, 70000.0, ts="t1"),
    ]
    results = compute_realized_pnl(orders)
    assert {r.venue for r in results} == {"US", "KR"}


def test_price_fallback_from_audit_extracts_kr_price():
    entries = [{
        "venue": "KR", "request": {"code": "005930", "side": "BUY", "price": 70000},
        "result": {"order_id": "1001", "status": "SUBMITTED", "filled": 0.0, "remaining": 1.0},
    }]
    assert price_fallback_from_audit(entries) == {("KR", "1001"): 70000.0}


def test_price_fallback_from_audit_handles_alpaca_id_field():
    entries = [{
        "venue": "US", "request": {"symbol": "AAPL", "side": "BUY", "limit_price": 190.5},
        "result": {"id": "uuid-123", "status": "accepted"},
    }]
    assert price_fallback_from_audit(entries) == {("US", "uuid-123"): 190.5}


def test_price_fallback_from_audit_skips_entries_without_price():
    entries = [{
        "venue": "US", "request": {"symbol": "AAPL", "side": "BUY", "order_type": "MARKET"},
        "result": {"id": "uuid-1", "status": "accepted"},
    }]
    assert price_fallback_from_audit(entries) == {}
