"""컨버전스 스코어링 순수함수 테스트 — 각 leg를 mock row로 주입."""
from unittest.mock import patch

from insider.convergence import compute_convergence


def _corp_action_row(ticker="005930", trade_type="BUYBACK", trade_date="2026-08-01"):
    return {"trade_type": trade_type, "ticker": ticker, "corp_name": "삼성전자",
            "trade_date": trade_date, "dart_url": "https://dart.fss.or.kr/x", "event_cause": "자사주"}


def _exec_row(stock_code="005930", trade_type="BUY", rcept_dt="2026-08-01"):
    return {"trade_type": trade_type, "stock_code": stock_code, "corp_name": "삼성전자",
            "rcept_dt": rcept_dt, "dart_url": "https://dart.fss.or.kr/y", "role": "대표이사", "event_cause": "장내매수"}


def test_single_leg_below_score_threshold_dropped():
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=[_exec_row()]), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[]):
        result = compute_convergence("kr", days=30)
    assert result == []


def test_two_legs_same_direction_score_two():
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=[_exec_row(trade_type="BUY")]), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[_corp_action_row(trade_type="BUYBACK")]):
        result = compute_convergence("kr", days=30)
    assert len(result) == 1
    sig = result[0]
    assert sig["ticker"] == "005930"
    assert sig["direction"] == "BULLISH"
    assert sig["score"] == 2
    assert {leg["source"] for leg in sig["legs"]} == {"dart_exec", "dart_corp_action"}


def test_two_legs_opposite_direction_not_convergence():
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=[_exec_row(trade_type="BUY")]), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[_corp_action_row(trade_type="DISPOSAL")]):
        result = compute_convergence("kr", days=30)
    assert result == []


def test_same_source_multiple_rows_counts_once():
    rows = [_exec_row(trade_type="BUY", rcept_dt="2026-08-01"), _exec_row(trade_type="BUY", rcept_dt="2026-07-30")]
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=rows), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[_corp_action_row(trade_type="BUYBACK")]):
        result = compute_convergence("kr", days=30)
    assert len(result) == 1
    assert result[0]["score"] == 2  # 2 sources, not 3 rows
    assert len(result[0]["legs"]) == 3  # all rows still listed


def test_excluded_trade_types_dropped_from_grouping():
    with patch("insider.convergence.get_recent_kr_insider_feed", return_value=[_exec_row(trade_type="HOLD_REPORT")]), \
         patch("insider.convergence.get_recent_kr_corporate_actions", return_value=[_corp_action_row(trade_type="RIGHTS_ISSUE")]):
        result = compute_convergence("kr", days=30)
    assert result == []


def test_us_market_form4_and_congress_converge():
    form4_row = {"trade_type": "SELL", "ticker": "TSLA", "issuer": "Tesla Inc",
                 "filing_date": "2026-08-01", "transaction_date": "2026-07-30"}
    congress_row = {"trade_type": "SELL", "ticker": "TSLA", "trade_date": "2026-07-29",
                    "chamber": "senate", "owner": "spouse", "link": "https://example.com/x"}
    with patch("insider.convergence.get_recent_form4_feed", return_value=[form4_row]), \
         patch("insider.convergence.get_congress_trades", return_value=[congress_row]), \
         patch("insider.convergence.get_unusual_options_activity", return_value=[]):
        result = compute_convergence("us", days=30)
    assert len(result) == 1
    assert result[0]["direction"] == "BEARISH"
    assert result[0]["score"] == 2


def test_options_uoa_adds_third_leg_to_existing_group():
    form4_row = {"trade_type": "BUY", "ticker": "TSLA", "issuer": "Tesla Inc",
                 "filing_date": "2026-08-01", "transaction_date": "2026-07-30"}
    congress_row = {"trade_type": "BUY", "ticker": "TSLA", "trade_date": "2026-07-29",
                    "chamber": "house", "owner": "self", "link": "https://example.com/y"}
    uoa_row = {"type": "call", "ticker": "TSLA", "expiration_date": "2026-08-15", "strike": 300.0}
    with patch("insider.convergence.get_recent_form4_feed", return_value=[form4_row]), \
         patch("insider.convergence.get_congress_trades", return_value=[congress_row]), \
         patch("insider.convergence.get_unusual_options_activity", return_value=[uoa_row]) as mock_uoa:
        result = compute_convergence("us", days=30)
    assert len(result) == 1
    assert result[0]["score"] == 3
    assert {leg["source"] for leg in result[0]["legs"]} == {"form4", "congress", "options_uoa"}
    mock_uoa.assert_called_once_with(["TSLA"])


def test_empty_ticker_universe_skips_uoa_call():
    with patch("insider.convergence.get_recent_form4_feed", return_value=[]), \
         patch("insider.convergence.get_congress_trades", return_value=[]), \
         patch("insider.convergence.get_unusual_options_activity") as mock_uoa:
        result = compute_convergence("us", days=30)
    assert result == []
    mock_uoa.assert_not_called()
