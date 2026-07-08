import datetime as dt

from research.polymarket_tick.market_selector import build_meta_by_token, select_target_markets

NOW = dt.datetime(2026, 7, 8, 12, 0, tzinfo=dt.timezone.utc)


def _market(condition_id="c1", liquidity=10000.0, end_date="2026-07-09",
            sports_market_type=None, game_start_time=None, clob_token_ids=("y1", "n1")):
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "event_id": "e1",
        "event_title": "", "end_date": end_date, "volume": 1000.0, "liquidity": liquidity,
        "yes_price": 0.5, "no_price": 0.5, "active": True, "closed": False,
        "accepting_orders": True, "clob_token_ids": clob_token_ids,
        "sports_market_type": sports_market_type, "game_start_time": game_start_time,
    }


def test_sports_market_in_progress_included():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time="2026-07-08 11:50:00+00")
    picked = select_target_markets([m], now=NOW)
    assert len(picked) == 1
    assert picked[0]["family"] == "sports"


def test_sports_market_upcoming_within_window_included():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time="2026-07-08 15:00:00+00")
    picked = select_target_markets([m], now=NOW)
    assert len(picked) == 1
    assert picked[0]["family"] == "sports"


def test_sports_market_before_window_excluded():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time="2026-07-08 08:00:00+00")
    assert select_target_markets([m], now=NOW) == []


def test_sports_market_after_window_excluded():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time="2026-07-08 17:00:00+00")
    assert select_target_markets([m], now=NOW) == []


def test_sports_market_missing_game_start_time_excluded():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time=None)
    assert select_target_markets([m], now=NOW) == []


def test_news_market_short_resolution_included():
    m = _market(end_date="2026-07-10")
    picked = select_target_markets([m], now=NOW)
    assert len(picked) == 1
    assert picked[0]["family"] == "news"


def test_news_market_long_resolution_excluded():
    m = _market(end_date="2026-12-31")
    assert select_target_markets([m], now=NOW) == []


def test_low_liquidity_excluded_even_if_otherwise_eligible():
    m = _market(liquidity=1000.0, end_date="2026-07-10")
    assert select_target_markets([m], now=NOW) == []


def test_build_meta_by_token_maps_yes_and_no_with_family():
    m = _market(condition_id="c1", end_date="2026-07-10", clob_token_ids=("y1", "n1"))
    picked = select_target_markets([m], now=NOW)
    meta = build_meta_by_token(picked)
    assert meta["y1"] == {"condition_id": "c1", "question": "q-c1", "family": "news", "outcome": "yes"}
    assert meta["n1"] == {"condition_id": "c1", "question": "q-c1", "family": "news", "outcome": "no"}
