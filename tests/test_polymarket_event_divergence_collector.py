import datetime as dt
from unittest.mock import patch

from research.polymarket_event_divergence import collector


def _market(condition_id, event_id="e1", event_title="이벤트", liquidity=10000.0,
            yes_price=0.5, end_date="2099-01-01", active=True, closed=False, accepting=True):
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "event_id": event_id,
        "event_title": event_title, "end_date": end_date, "liquidity": liquidity,
        "yes_price": yes_price, "active": active, "closed": closed, "accepting_orders": accepting,
    }


def test_group_by_event_groups_and_drops_singletons():
    markets = [
        _market("a1", event_id="e1"), _market("a2", event_id="e1"),
        _market("b1", event_id="e2"),
        _market("c1", event_id="e3"), _market("c2", event_id="e3"), _market("c3", event_id="e3"),
    ]
    groups = collector.group_by_event(markets)
    assert set(groups.keys()) == {"e1", "e3"}
    assert len(groups["e1"]) == 2
    assert len(groups["e3"]) == 3


def test_group_by_event_skips_markets_without_event_id():
    markets = [_market("a1", event_id=""), _market("a2", event_id="")]
    assert collector.group_by_event(markets) == {}


def test_compute_divergence_calculates_yes_sum_and_divergence():
    markets = [_market("a", yes_price=0.55, liquidity=6000.0),
               _market("b", yes_price=0.52, liquidity=6000.0)]
    snap = collector.compute_divergence(markets)
    assert snap["yes_sum"] == 1.07
    assert snap["divergence"] == 0.07
    assert snap["event_id"] == "e1"
    assert snap["event_title"] == "이벤트"
    assert snap["n_markets"] == 2
    assert snap["total_liquidity"] == 12000.0
    assert [m["condition_id"] for m in snap["markets"]] == ["a", "b"]
    assert "ts" in snap


def test_compute_divergence_returns_none_for_single_market():
    assert collector.compute_divergence([_market("a")]) is None


def test_compute_divergence_returns_none_when_liquidity_sum_below_min():
    markets = [_market("a", liquidity=2000.0), _market("b", liquidity=2000.0)]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_any_market_inactive():
    markets = [_market("a"), _market("b", active=False)]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_any_market_not_accepting_orders():
    markets = [_market("a"), _market("b", accepting=False)]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_any_market_missing_yes_price():
    markets = [_market("a"), _market("b", yes_price=None)]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_end_date_malformed():
    markets = [_market("a"), _market("b", end_date="not-a-date")]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_any_market_too_close_to_resolution():
    near_date = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    markets = [_market("a"), _market("b", end_date=near_date)]
    assert collector.compute_divergence(markets) is None


def test_run_once_sorts_by_absolute_divergence_and_respects_top_n():
    markets = [
        _market("a1", event_id="e1", yes_price=0.50),
        _market("a2", event_id="e1", yes_price=0.48),
        _market("b1", event_id="e2", yes_price=0.50),
        _market("b2", event_id="e2", yes_price=0.70),
    ]
    with patch.object(collector, "get_markets", return_value=markets):
        snaps = collector.run_once(top_n=1)
    assert len(snaps) == 1
    assert snaps[0]["event_id"] == "e2"


def test_run_once_skips_events_that_fail_filters():
    markets = [_market("a1", event_id="e1"), _market("a2", event_id="e1", active=False)]
    with patch.object(collector, "get_markets", return_value=markets):
        snaps = collector.run_once()
    assert snaps == []
