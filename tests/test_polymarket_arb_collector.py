from unittest.mock import MagicMock, patch

from research.polymarket_arb import collector


def _market(condition_id="c1", liquidity=10000.0, yes_price=0.5, no_price=0.5,
            end_date="2099-01-01", clob_token_ids=("y1", "n1"), active=True,
            closed=False, accepting=True):
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "event_id": "e1",
        "event_title": "", "end_date": end_date, "volume": 1000.0, "liquidity": liquidity,
        "yes_price": yes_price, "no_price": no_price, "active": active, "closed": closed,
        "accepting_orders": accepting, "clob_token_ids": clob_token_ids,
    }


def _book(bids, asks):
    return {"bids": [{"price": str(p), "size": str(s)} for p, s in bids],
            "asks": [{"price": str(p), "size": str(s)} for p, s in asks]}


def test_select_liquid_markets_filters_and_sorts_by_liquidity():
    markets = [
        _market(condition_id="low_liquidity", liquidity=3000.0),
        _market(condition_id="extreme_price", yes_price=0.95),
        _market(condition_id="no_clob", clob_token_ids=(None, None)),
        _market(condition_id="inactive", active=False),
        _market(condition_id="b", liquidity=8000.0),
        _market(condition_id="a", liquidity=20000.0),
    ]
    with patch.object(collector, "get_markets", return_value=markets):
        picked = collector.select_liquid_markets(top_n=10)
    assert [m["condition_id"] for m in picked] == ["a", "b"]


def test_select_liquid_markets_respects_top_n():
    markets = [_market(condition_id=str(i), liquidity=float(1000 * i)) for i in range(10, 20)]
    with patch.object(collector, "get_markets", return_value=markets):
        picked = collector.select_liquid_markets(top_n=3)
    assert len(picked) == 3
    assert picked[0]["condition_id"] == "19"


def test_best_levels_picks_best_bid_and_ask_with_size():
    book = _book(bids=[(0.40, 5), (0.45, 8)], asks=[(0.55, 12), (0.60, 3)])
    levels = collector.best_levels(book)
    assert levels == {"bid": 0.45, "bid_size": 8.0, "ask": 0.55, "ask_size": 12.0}


def test_best_levels_handles_empty_book():
    levels = collector.best_levels({"bids": [], "asks": []})
    assert levels == {"bid": None, "bid_size": None, "ask": None, "ask_size": None}


def test_fetch_book_returns_json_on_200():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"bids": [], "asks": []}
    resp.raise_for_status.return_value = None
    with patch.object(collector.requests, "get", return_value=resp):
        book = collector.fetch_book("tok1")
    assert book == {"bids": [], "asks": []}


def test_fetch_book_returns_none_after_retries_exhausted():
    with patch.object(collector.requests, "get", side_effect=Exception("boom")), \
         patch.object(collector.time, "sleep"):
        book = collector.fetch_book("tok1", retries=2)
    assert book is None


def test_snapshot_market_builds_full_record():
    market = _market(condition_id="c1", liquidity=9000.0, clob_token_ids=("y1", "n1"))
    yes_book = _book(bids=[(0.40, 10)], asks=[(0.45, 20)])
    no_book = _book(bids=[(0.48, 15)], asks=[(0.50, 25)])
    with patch.object(collector, "fetch_book", side_effect=[yes_book, no_book]):
        snap = collector.snapshot_market(market)
    assert snap["condition_id"] == "c1"
    assert snap["yes_ask"] == 0.45
    assert snap["yes_ask_size"] == 20.0
    assert snap["no_ask"] == 0.50
    assert snap["no_ask_size"] == 25.0
    assert snap["sum_ask"] == 0.95
    assert snap["is_opportunity"] is True
    assert snap["liquidity"] == 9000.0
    assert "ts" in snap


def test_snapshot_market_returns_none_when_book_fetch_fails():
    market = _market(clob_token_ids=("y1", "n1"))
    with patch.object(collector, "fetch_book", side_effect=[None, _book([(0.5, 1)], [(0.55, 1)])]):
        snap = collector.snapshot_market(market)
    assert snap is None


def test_run_once_collects_snapshots_for_selected_markets():
    markets = [_market(condition_id="a", liquidity=10000.0), _market(condition_id="b", liquidity=9000.0)]
    fake_snap = {"condition_id": "x"}
    with patch.object(collector, "select_liquid_markets", return_value=markets), \
         patch.object(collector, "snapshot_market", return_value=fake_snap):
        snaps = collector.run_once()
    assert snaps == [fake_snap, fake_snap]


def test_run_once_skips_markets_where_snapshot_fails():
    markets = [_market(condition_id="a"), _market(condition_id="b")]
    with patch.object(collector, "select_liquid_markets", return_value=markets), \
         patch.object(collector, "snapshot_market", side_effect=[None, {"condition_id": "b"}]):
        snaps = collector.run_once()
    assert snaps == [{"condition_id": "b"}]
