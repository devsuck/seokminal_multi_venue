"""Tests for Hyperliquid public API client — all HTTP calls mocked."""
from unittest.mock import MagicMock, patch

import pytest

from hyperliquid.client import get_all_mids, get_candles, get_l2_book, get_meta_and_ctxs

HL_URL = "https://api.hyperliquid.xyz/info"

MOCK_MIDS = {"BTC": "94500.0", "ETH": "3200.0", "SOL": "180.0"}

MOCK_META = {
    "universe": [
        {"name": "BTC", "szDecimals": 5, "maxLeverage": 50},
        {"name": "ETH", "szDecimals": 4, "maxLeverage": 25},
    ]
}

MOCK_CTXS = [
    {
        "funding": "0.0001",
        "openInterest": "5000.0",
        "prevDayPx": "93000.0",
        "dayNtlVlm": "500000000.0",
        "markPx": "94500.0",
        "midPx": "94500.0",
    },
    {
        "funding": "-0.00005",
        "openInterest": "20000.0",
        "prevDayPx": "3100.0",
        "dayNtlVlm": "200000000.0",
        "markPx": "3200.0",
        "midPx": "3200.0",
    },
]

MOCK_CANDLES = [
    {
        "t": 1700000000000,
        "T": 1700086399000,
        "s": "BTC",
        "i": "1d",
        "o": "93000.0",
        "c": "94500.0",
        "h": "95000.0",
        "l": "92000.0",
        "v": "123.45",
        "n": 5678,
    }
]

MOCK_BOOK = {
    "coin": "BTC",
    "time": 1700000000000,
    "levels": [
        [{"px": "94490.0", "sz": "0.5", "n": 3}, {"px": "94480.0", "sz": "1.0", "n": 5}],
        [{"px": "94510.0", "sz": "0.3", "n": 2}, {"px": "94520.0", "sz": "0.8", "n": 4}],
    ],
}


def _mock_response(json_data):
    mock = MagicMock()
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    return mock


# ── get_all_mids ──────────────────────────────────────────────────────────────

def test_get_all_mids_returns_dict():
    with patch("hyperliquid.client.requests.post") as mock_post:
        mock_post.return_value = _mock_response(MOCK_MIDS)
        result = get_all_mids()
    assert isinstance(result, dict)
    assert "BTC" in result
    assert result["BTC"] == "94500.0"


def test_get_all_mids_posts_correct_payload():
    with patch("hyperliquid.client.requests.post") as mock_post:
        mock_post.return_value = _mock_response(MOCK_MIDS)
        get_all_mids()
    mock_post.assert_called_once_with(HL_URL, json={"type": "allMids"}, timeout=10)


# ── get_meta_and_ctxs ─────────────────────────────────────────────────────────

def test_get_meta_and_ctxs_returns_lists():
    with patch("hyperliquid.client.requests.post") as mock_post:
        mock_post.return_value = _mock_response([MOCK_META, MOCK_CTXS])
        universe, ctxs = get_meta_and_ctxs()
    assert isinstance(universe, list)
    assert isinstance(ctxs, list)
    assert universe[0]["name"] == "BTC"


def test_get_meta_and_ctxs_equal_lengths():
    with patch("hyperliquid.client.requests.post") as mock_post:
        mock_post.return_value = _mock_response([MOCK_META, MOCK_CTXS])
        universe, ctxs = get_meta_and_ctxs()
    assert len(universe) == len(ctxs)


# ── get_candles ───────────────────────────────────────────────────────────────

def test_get_candles_returns_list():
    with patch("hyperliquid.client.requests.post") as mock_post:
        mock_post.return_value = _mock_response(MOCK_CANDLES)
        result = get_candles("BTC", "1d", 1699000000000, 1700000000000)
    assert isinstance(result, list)
    assert len(result) == 1


def test_get_candles_required_keys():
    with patch("hyperliquid.client.requests.post") as mock_post:
        mock_post.return_value = _mock_response(MOCK_CANDLES)
        result = get_candles("BTC", "1d", 1699000000000, 1700000000000)
    required = {"t", "o", "c", "h", "l", "v", "n"}
    assert required <= set(result[0].keys())


def test_get_candles_posts_correct_payload():
    with patch("hyperliquid.client.requests.post") as mock_post:
        mock_post.return_value = _mock_response(MOCK_CANDLES)
        get_candles("BTC", "1d", 1699000000000, 1700000000000)
    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]["json"]
    assert payload["type"] == "candleSnapshot"
    assert payload["req"]["coin"] == "BTC"
    assert payload["req"]["interval"] == "1d"
    assert payload["req"]["startTime"] == 1699000000000
    assert payload["req"]["endTime"] == 1700000000000


# ── get_l2_book ───────────────────────────────────────────────────────────────

def test_get_l2_book_returns_dict_with_coin():
    with patch("hyperliquid.client.requests.post") as mock_post:
        mock_post.return_value = _mock_response(MOCK_BOOK)
        result = get_l2_book("BTC")
    assert isinstance(result, dict)
    assert result["coin"] == "BTC"


def test_get_l2_book_has_two_sides():
    with patch("hyperliquid.client.requests.post") as mock_post:
        mock_post.return_value = _mock_response(MOCK_BOOK)
        result = get_l2_book("BTC")
    assert "levels" in result
    assert len(result["levels"]) == 2
    assert len(result["levels"][0]) > 0   # bids
    assert len(result["levels"][1]) > 0   # asks
