"""Polymarket 페이퍼 다각화 배스킷 봇 테스트."""
from unittest.mock import patch

from api_server import polymarket_bot as bot


def _cfg(**over):
    return {**bot._DEFAULT, "enabled": True, "positions": [], **over}


def _market(condition_id="c1", event_id="e1", yes=0.5, no=0.5, liquidity=10000.0,
            end_date="2099-01-01", active=True, closed=False, accepting=True,
            days_out=None):
    if days_out is not None:
        import datetime as _dt
        end_date = (_dt.date.today() + _dt.timedelta(days=days_out)).isoformat()
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "event_id": event_id,
        "event_title": "", "end_date": end_date, "volume": 1000.0, "liquidity": liquidity,
        "yes_price": yes, "no_price": no, "active": active, "closed": closed,
        "accepting_orders": accepting,
    }


def test_scan_and_enter_picks_favorite_side():
    cfg = _cfg(per_market_usd=10.0, budget=100.0)
    with patch.object(bot, "get_markets", return_value=[_market(yes=0.7, no=0.3, days_out=10)]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 1
    pos = cfg["positions"][0]
    assert pos["side"] == "YES"
    assert pos["entry_price"] == 0.7
    assert pos["usd"] == 10.0
    assert cfg["spent"] == 10.0


def test_scan_and_enter_skips_too_far_maturity():
    cfg = _cfg(max_days_to_resolution=30)
    with patch.object(bot, "get_markets", return_value=[_market(days_out=90)]):
        entered = bot._scan_and_enter(cfg)
    assert entered == 0
    assert cfg["positions"] == []


def test_scan_and_enter_skips_extreme_price():
    cfg = _cfg(min_price=0.10, max_price=0.90)
    with patch.object(bot, "get_markets", return_value=[_market(yes=0.98, no=0.02)]):
        entered = bot._scan_and_enter(cfg)
    assert entered == 0
    assert cfg["positions"] == []


def test_scan_and_enter_skips_low_liquidity():
    cfg = _cfg(min_liquidity=5000.0)
    with patch.object(bot, "get_markets", return_value=[_market(liquidity=100.0)]):
        entered = bot._scan_and_enter(cfg)
    assert entered == 0


def test_scan_and_enter_skips_duplicate_event():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "other", "event_id": "e1", "question": "x",
                          "side": "YES", "entry_price": 0.5, "usd": 10.0, "shares": 20.0,
                          "end_date": "2099-01-01", "entry_ts": ""}]
    with patch.object(bot, "get_markets", return_value=[_market(condition_id="c2", event_id="e1")]):
        entered = bot._scan_and_enter(cfg)
    assert entered == 0


def test_scan_and_enter_respects_budget():
    cfg = _cfg(budget=15.0, per_market_usd=10.0, spent=10.0)
    with patch.object(bot, "get_markets", return_value=[_market()]):
        entered = bot._scan_and_enter(cfg)
    assert entered == 0  # remaining=5 < per_market_usd=10


def test_process_resolutions_pays_out_winner():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "c1", "question": "q", "event_id": "e1",
                          "side": "YES", "entry_price": 0.4, "usd": 10.0, "shares": 25.0,
                          "end_date": "2020-01-01", "entry_ts": ""}]
    cfg["spent"] = 10.0
    resolved_market = _market(condition_id="c1", yes=0.99, no=0.01, closed=True)
    with patch.object(bot, "get_market", return_value=resolved_market), \
         patch.object(bot, "_log_event"):
        resolved = bot._process_resolutions(cfg)
    assert resolved == 1
    assert cfg["positions"] == []
    assert cfg["spent"] == 0.0
    assert cfg["realized_pnl"] == round((1.0 - 0.4) * 25.0, 2)


def test_process_resolutions_pays_out_loser():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "c1", "question": "q", "event_id": "e1",
                          "side": "YES", "entry_price": 0.6, "usd": 12.0, "shares": 20.0,
                          "end_date": "2020-01-01", "entry_ts": ""}]
    cfg["spent"] = 12.0
    resolved_market = _market(condition_id="c1", yes=0.02, no=0.98, closed=True)
    with patch.object(bot, "get_market", return_value=resolved_market), \
         patch.object(bot, "_log_event"):
        resolved = bot._process_resolutions(cfg)
    assert resolved == 1
    assert cfg["realized_pnl"] == round((0.0 - 0.6) * 20.0, 2)


def test_process_resolutions_keeps_open_positions():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "c1", "question": "q", "event_id": "e1",
                          "side": "YES", "entry_price": 0.5, "usd": 10.0, "shares": 20.0,
                          "end_date": "2099-01-01", "entry_ts": ""}]
    with patch.object(bot, "get_market", return_value=_market(condition_id="c1", closed=False)):
        resolved = bot._process_resolutions(cfg)
    assert resolved == 0
    assert len(cfg["positions"]) == 1


def test_tick_disabled_skips():
    cfg = bot._DEFAULT
    with patch.object(bot, "_load", return_value=dict(cfg)):
        result = bot.tick()
    assert result == {"skipped": "disabled"}
