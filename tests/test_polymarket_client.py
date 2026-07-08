from polymarket.client import _map_market


def _raw_market(**over):
    base = {
        "conditionId": "c1", "question": "q", "events": [{"id": "e1", "title": "t"}],
        "endDateIso": "2099-01-01", "volumeNum": 100.0, "liquidityNum": 5000.0,
        "outcomes": ["Yes", "No"], "outcomePrices": ["0.6", "0.4"],
        "active": True, "closed": False, "acceptingOrders": True,
    }
    base.update(over)
    return base


def test_map_market_extracts_clob_token_ids():
    mapped = _map_market(_raw_market(clobTokenIds='["111", "222"]'))
    assert mapped["clob_token_ids"] == ("111", "222")


def test_map_market_missing_clob_token_ids_defaults_to_none_pair():
    mapped = _map_market(_raw_market())
    assert mapped["clob_token_ids"] == (None, None)


def test_map_market_malformed_clob_token_ids_defaults_to_none_pair():
    mapped = _map_market(_raw_market(clobTokenIds='["only-one"]'))
    assert mapped["clob_token_ids"] == (None, None)


def test_map_market_still_returns_none_for_non_binary_outcomes():
    mapped = _map_market(_raw_market(outcomes=["A", "B", "C"], outcomePrices=["0.3", "0.3", "0.4"]))
    assert mapped is None


def test_map_market_extracts_sports_market_type_and_game_start_time():
    mapped = _map_market(_raw_market(
        sportsMarketType="soccer_halftime_result",
        gameStartTime="2026-07-08 17:00:00+00",
    ))
    assert mapped["sports_market_type"] == "soccer_halftime_result"
    assert mapped["game_start_time"] == "2026-07-08 17:00:00+00"


def test_map_market_defaults_sports_fields_to_none():
    mapped = _map_market(_raw_market())
    assert mapped["sports_market_type"] is None
    assert mapped["game_start_time"] is None
