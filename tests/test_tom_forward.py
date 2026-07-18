"""KR turn-of-month portfolio forward-test 모듈 테스트 (동결 config + 순수 헬퍼)."""
from __future__ import annotations

from research.paper import tom_config as CFG
from research.paper.tom_forward import _at, _month_end_days


def test_config_frozen_constants():
    assert CFG.HOLD_DAYS == 4
    assert CFG.COST_BASE_BPS == 40.0
    assert CFG.STATUS == "paper_candidate_yellow"


def _bar(dates):
    return {"dates": dates}


def test_month_end_days_picks_last_trading_day_per_month():
    liquid = [_bar(["2025-01-30", "2025-01-31", "2025-02-27", "2025-02-28", "2025-03-03"])]
    assert _month_end_days(liquid) == ["2025-01-31", "2025-02-28"]


def test_month_end_days_empty_when_no_liquid_universe():
    assert _month_end_days([]) == []


def test_at_returns_index_of_latest_bar_on_or_before_date():
    b = {"dates": ["2025-01-01", "2025-01-05", "2025-01-10"]}
    assert _at(b, "2025-01-07") == 1
    assert _at(b, "2025-01-01") == 0


def test_at_returns_none_before_first_bar():
    b = {"dates": ["2025-01-05", "2025-01-10"]}
    assert _at(b, "2025-01-01") is None
