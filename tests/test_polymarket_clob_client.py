"""Polymarket CLOB 오더북 읽기전용 클라이언트 테스트."""
from unittest.mock import patch

import pytest

from polymarket import clob_client


def _book(bids, asks):
    return {"bids": bids, "asks": asks}


def test_get_order_book_returns_best_bid_ask():
    raw = _book(
        [{"price": "0.48", "size": "100"}, {"price": "0.50", "size": "50"}],
        [{"price": "0.53", "size": "80"}, {"price": "0.55", "size": "20"}],
    )
    with patch.object(clob_client, "_get", return_value=raw):
        book = clob_client.get_order_book("tok1")
    assert book == {"best_bid": 0.50, "best_ask": 0.53}


def test_get_order_book_empty_book_returns_none():
    with patch.object(clob_client, "_get", return_value=_book([], [])):
        assert clob_client.get_order_book("tok1") is None


def test_get_order_book_request_failure_returns_none():
    with patch.object(clob_client, "_get", side_effect=Exception("boom")):
        assert clob_client.get_order_book("tok1") is None


def test_spread_bps_from_book():
    book = {"best_bid": 0.50, "best_ask": 0.53}
    assert clob_client.spread_bps_from_book(book) == pytest.approx((0.53 - 0.50) / 0.515 * 10_000.0)


def test_spread_bps_from_book_none_input_returns_none():
    assert clob_client.spread_bps_from_book(None) is None


def test_spread_bps_from_book_inverted_market_returns_none():
    assert clob_client.spread_bps_from_book({"best_bid": 0.6, "best_ask": 0.5}) is None
