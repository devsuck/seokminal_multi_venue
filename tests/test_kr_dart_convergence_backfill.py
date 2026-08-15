"""kr_dart_convergence_backfill 순수 로직(그룹핑 + 방향성 수익률 부호반전) 테스트."""
from unittest.mock import patch

from research.data.kr_dart_convergence_backfill import backtest, group_by_ticker_direction


def _leg(source, ticker="005930", direction="BULLISH", trade_date="2026-07-01"):
    return {"source": source, "ticker": ticker, "direction": direction, "trade_date": trade_date}


def test_group_by_ticker_direction_scores_by_distinct_sources_not_row_count():
    legs = [_leg("dart_exec", trade_date="2026-07-02"), _leg("dart_exec", trade_date="2026-07-01"),
            _leg("dart_corp_action", trade_date="2026-07-03")]
    groups = group_by_ticker_direction(legs)
    assert len(groups) == 1
    g = groups[0]
    assert g["score"] == 2  # 2 distinct sources, 3 rows
    assert g["n_legs"] == 3
    assert g["signal_date"] == "20260701"  # earliest trade_date across all legs


def test_group_by_ticker_direction_splits_by_direction():
    legs = [_leg("dart_exec", direction="BULLISH"), _leg("dart_corp_action", direction="BEARISH")]
    groups = group_by_ticker_direction(legs)
    assert len(groups) == 2
    assert {g["score"] for g in groups} == {1, 1}


def test_backtest_keeps_raw_return_for_bullish_directional_return():
    groups = [{"ticker": "005930", "direction": "BULLISH", "score": 2, "signal_date": "20260701", "n_legs": 2}]
    with patch("research.data.kr_dart_convergence_backfill._forward_return", return_value=0.05):
        result = backtest(groups)
    assert result["converged_2plus"]["n"] == 1
    assert result["rows_converged"][0]["directional_return"] == 0.05


def test_backtest_flips_sign_for_bearish_directional_return():
    """BEARISH 신호는 가격이 내려가야 '적중' — directional_return = -raw_return."""
    groups = [{"ticker": "005930", "direction": "BEARISH", "score": 1, "signal_date": "20260701", "n_legs": 1}]
    with patch("research.data.kr_dart_convergence_backfill._forward_return", return_value=0.05):
        result = backtest(groups)
    assert result["single_source"]["n"] == 1
    assert result["rows_single"][0]["directional_return"] == -0.05


def test_backtest_skips_groups_with_no_price_data():
    groups = [{"ticker": "999999", "direction": "BULLISH", "score": 2, "signal_date": "20260701", "n_legs": 2}]
    with patch("research.data.kr_dart_convergence_backfill._forward_return", return_value=None):
        result = backtest(groups)
    assert result["converged_2plus"]["n"] == 0
