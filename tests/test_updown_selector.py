import datetime as dt

from research.polymarket_arb import updown_selector as sel

_NOW = dt.datetime(2026, 7, 13, 21, 10, 0, tzinfo=dt.timezone.utc)


def _market(condition_id="c1", slug="btc-updown-5m-1783991400", liquidity=1000.0,
            end_datetime="2026-07-13T21:15:00Z", clob_token_ids=("y1", "n1"),
            active=True, closed=False, accepting=True):
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "slug": slug,
        "end_date": (end_datetime or "")[:10], "end_datetime": end_datetime,
        "volume": 0.0, "liquidity": liquidity, "yes_price": 0.5, "no_price": 0.5,
        "active": active, "closed": closed, "accepting_orders": accepting,
        "clob_token_ids": clob_token_ids,
    }


def test_selects_market_matching_all_criteria():
    markets = [_market(condition_id="a")]
    picked = sel.select_updown_markets(markets, now=_NOW)
    assert [m["condition_id"] for m in picked] == ["a"]


def test_rejects_non_updown_slug():
    markets = [_market(condition_id="a", slug="btc-hourly-open-1783991400")]
    picked = sel.select_updown_markets(markets, now=_NOW)
    assert picked == []


def test_rejects_below_liquidity_floor():
    markets = [_market(condition_id="a", liquidity=100.0)]
    picked = sel.select_updown_markets(markets, now=_NOW, min_liquidity=500.0)
    assert picked == []


def test_rejects_resolution_too_far_in_future():
    markets = [_market(condition_id="a", end_datetime="2026-07-14T21:15:00Z")]
    picked = sel.select_updown_markets(markets, now=_NOW, max_minutes_to_resolve=15.0)
    assert picked == []


def test_rejects_already_past_resolution():
    markets = [_market(condition_id="a", end_datetime="2026-07-13T21:05:00Z")]
    picked = sel.select_updown_markets(markets, now=_NOW)
    assert picked == []


def test_rejects_missing_clob_token_ids():
    markets = [_market(condition_id="a", clob_token_ids=(None, None))]
    picked = sel.select_updown_markets(markets, now=_NOW)
    assert picked == []


def test_rejects_inactive_or_closed_or_not_accepting():
    markets = [
        _market(condition_id="inactive", active=False),
        _market(condition_id="closed", closed=True),
        _market(condition_id="no_orders", accepting=False),
    ]
    picked = sel.select_updown_markets(markets, now=_NOW)
    assert picked == []


def test_sorts_by_liquidity_descending():
    markets = [
        _market(condition_id="low", liquidity=1500.0),
        _market(condition_id="high", liquidity=5000.0),
    ]
    picked = sel.select_updown_markets(markets, now=_NOW)
    assert [m["condition_id"] for m in picked] == ["high", "low"]
