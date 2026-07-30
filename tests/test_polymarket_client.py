from unittest.mock import patch

from polymarket.client import _map_market, get_markets


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


def test_map_market_extracts_slug_and_full_precision_end_datetime():
    # 실제 API: endDate가 전체정밀도(ISO datetime), endDateIso는 날짜만 truncate됨.
    mapped = _map_market(_raw_market(
        slug="btc-updown-5m-1783991400",
        endDateIso="2026-07-13",
        endDate="2026-07-13T21:15:00Z",
    ))
    assert mapped["slug"] == "btc-updown-5m-1783991400"
    assert mapped["end_datetime"] == "2026-07-13T21:15:00Z"
    assert mapped["end_date"] == "2026-07-13"


def test_map_market_slug_and_end_datetime_default_to_empty_string():
    mapped = _map_market(_raw_market(endDateIso="", endDate=""))
    assert mapped["slug"] == ""
    assert mapped["end_datetime"] == ""
    assert mapped["end_date"] == ""


def test_get_markets_paginates_past_gamma_100_cap():
    """2026-07-30 실측: Gamma API가 limit>100을 조용히 100개로 잘라버림.
    limit=250 요청 시 offset 0/100/200으로 3번 나눠 불러 250개 다 채워야 한다."""
    calls = []

    def fake_get(path, params):
        calls.append(dict(params))
        offset, page_limit = params["offset"], params["limit"]
        return [_raw_market(conditionId=f"c{offset + i}") for i in range(page_limit)]

    with patch("polymarket.client._get", side_effect=fake_get):
        result = get_markets(limit=250)

    assert len(result) == 250
    assert [c["offset"] for c in calls] == [0, 100, 200]
    assert [c["limit"] for c in calls] == [100, 100, 50]


def test_get_markets_stops_paginating_when_data_exhausted():
    """실제 시장이 limit보다 적으면(짧은 페이지 응답) 거기서 멈춰야 함 — 무한 재요청 방지."""

    def fake_get(path, params):
        offset, page_limit = params["offset"], params["limit"]
        remaining = max(0, 120 - offset)
        n = min(page_limit, remaining)
        return [_raw_market(conditionId=f"c{offset + i}") for i in range(n)]

    with patch("polymarket.client._get", side_effect=fake_get):
        result = get_markets(limit=300)

    assert len(result) == 120
