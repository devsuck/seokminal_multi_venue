"""Polymarket AI 판단 봇(side="ai") 테스트."""
from unittest.mock import MagicMock, patch

from api_server import polymarket_ai_bot as bot


def _cfg(**over):
    return {**bot._DEFAULT, "enabled": True, "positions": [], **over}


def _market(condition_id="c1", event_id="e1", yes=0.5, no=0.5, liquidity=10000.0,
            end_date="2099-01-01", active=True, closed=False, accepting=True,
            days_out=None, question=None):
    if days_out is not None:
        import datetime as _dt
        end_date = (_dt.date.today() + _dt.timedelta(days=days_out)).isoformat()
    return {
        "condition_id": condition_id, "question": question or f"q-{condition_id}", "event_id": event_id,
        "event_title": "", "end_date": end_date, "volume": 1000.0, "liquidity": liquidity,
        "yes_price": yes, "no_price": no, "active": active, "closed": closed,
        "accepting_orders": accepting,
    }


def _judgment(yes_prob):
    return {"yes_prob": yes_prob, "reasoning": "r"}


def test_scan_candidates_skips_low_liquidity():
    cfg = _cfg(min_liquidity=5000.0)
    with patch.object(bot, "get_markets", return_value=[_market(liquidity=100.0)]):
        candidates = bot._scan_candidates(cfg)
    assert candidates == []


def test_scan_candidates_skips_extreme_price():
    cfg = _cfg(min_price=0.10, max_price=0.90)
    with patch.object(bot, "get_markets", return_value=[_market(yes=0.98, no=0.02)]):
        candidates = bot._scan_candidates(cfg)
    assert candidates == []


def test_scan_candidates_skips_too_far_maturity():
    cfg = _cfg(max_days_to_resolution=30)
    with patch.object(bot, "get_markets", return_value=[_market(days_out=90)]):
        candidates = bot._scan_candidates(cfg)
    assert candidates == []


def test_scan_candidates_skips_already_held_event():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "other", "event_id": "e1", "question": "x",
                          "side": "YES", "entry_price": 0.5, "usd": 10.0, "shares": 20.0,
                          "end_date": "2099-01-01", "entry_ts": "", "ai_yes_prob": 0.6, "edge": 0.1}]
    with patch.object(bot, "get_markets", return_value=[_market(condition_id="c2", event_id="e1")]):
        candidates = bot._scan_candidates(cfg)
    assert candidates == []


def test_scan_candidates_passes_valid_market():
    cfg = _cfg()
    with patch.object(bot, "get_markets", return_value=[_market(days_out=10)]):
        candidates = bot._scan_candidates(cfg)
    assert len(candidates) == 1
    assert candidates[0]["condition_id"] == "c1"


def test_judge_and_enter_enters_yes_when_ai_above_market():
    cfg = _cfg(per_market_usd=10.0, budget=100.0, min_edge=0.05)
    market = _market(yes=0.5, no=0.5, days_out=10)
    judged = [{**market, "judgment": _judgment(0.7)}]  # edge = +0.2
    with patch.object(bot, "_scan_candidates", return_value=[market]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 1}, 1)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"), \
         patch.object(bot, "_log_event"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 1
    pos = cfg["positions"][0]
    assert pos["side"] == "YES"
    assert pos["entry_price"] == 0.5
    assert pos["ai_yes_prob"] == 0.7
    assert pos["edge"] == 0.2
    assert cfg["spent"] == 10.0


def test_judge_and_enter_enters_no_when_ai_below_market():
    cfg = _cfg(per_market_usd=10.0, budget=100.0, min_edge=0.05)
    market = _market(yes=0.6, no=0.4, days_out=10)
    judged = [{**market, "judgment": _judgment(0.3)}]  # edge = -0.3
    with patch.object(bot, "_scan_candidates", return_value=[market]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 1}, 1)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"), \
         patch.object(bot, "_log_event"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 1
    pos = cfg["positions"][0]
    assert pos["side"] == "NO"
    assert pos["entry_price"] == 0.4
    assert pos["edge"] == -0.3


def test_judge_and_enter_skips_when_edge_below_threshold():
    cfg = _cfg(per_market_usd=10.0, budget=100.0, min_edge=0.05)
    market = _market(yes=0.5, no=0.5, days_out=10)
    judged = [{**market, "judgment": _judgment(0.52)}]  # edge = 0.02 < 0.05
    with patch.object(bot, "_scan_candidates", return_value=[market]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 1}, 1)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 0
    assert cfg["positions"] == []


def test_judge_and_enter_skips_when_judgment_none():
    cfg = _cfg(per_market_usd=10.0, budget=100.0)
    market = _market(days_out=10)
    judged = [{**market, "judgment": None}]
    with patch.object(bot, "_scan_candidates", return_value=[market]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 0}, 0)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 0


def test_judge_and_enter_respects_budget():
    cfg = _cfg(budget=15.0, per_market_usd=10.0, spent=10.0)
    market = _market(days_out=10)
    with patch.object(bot, "_scan_candidates", return_value=[market]):
        entered = bot._judge_and_enter(cfg)
    assert entered == 0  # remaining=5 < per_market_usd=10, _scan_candidates 호출 전에 리턴


def test_judge_and_enter_skips_duplicate_event_within_tick():
    cfg = _cfg(per_market_usd=10.0, budget=100.0, min_edge=0.05, max_positions=5)
    m1 = _market(condition_id="c1", event_id="e1", yes=0.5, no=0.5, days_out=10)
    m2 = _market(condition_id="c2", event_id="e1", yes=0.5, no=0.5, days_out=10)
    judged = [{**m1, "judgment": _judgment(0.8)}, {**m2, "judgment": _judgment(0.8)}]
    with patch.object(bot, "_scan_candidates", return_value=[m1, m2]), \
         patch.object(bot._judge, "load_cache", return_value={}), \
         patch.object(bot._judge, "load_daily_state", return_value={"date": "x", "calls_used": 0}), \
         patch.object(bot._judge, "judge_markets", return_value=(judged, {}, {"date": "x", "calls_used": 2}, 2)), \
         patch.object(bot._judge, "save_cache"), patch.object(bot._judge, "save_daily_state"), \
         patch.object(bot, "_log_event"):
        entered = bot._judge_and_enter(cfg)
    assert entered == 1  # 두번째는 같은 event_id라 스킵


def test_process_resolutions_pays_out_winner():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "c1", "question": "q", "event_id": "e1",
                          "side": "YES", "entry_price": 0.4, "usd": 10.0, "shares": 25.0,
                          "end_date": "2020-01-01", "entry_ts": "", "ai_yes_prob": 0.7, "edge": 0.3}]
    cfg["spent"] = 10.0
    resolved_market = _market(condition_id="c1", yes=0.99, no=0.01, closed=True)
    with patch.object(bot, "get_market", return_value=resolved_market), \
         patch.object(bot, "_log_event"):
        resolved = bot._process_resolutions(cfg)
    assert resolved == 1
    assert cfg["positions"] == []
    assert cfg["spent"] == 0.0
    assert cfg["realized_pnl"] == round((1.0 - 0.4) * 25.0, 2)


def test_process_resolutions_keeps_open_positions():
    cfg = _cfg()
    cfg["positions"] = [{"condition_id": "c1", "question": "q", "event_id": "e1",
                          "side": "YES", "entry_price": 0.5, "usd": 10.0, "shares": 20.0,
                          "end_date": "2099-01-01", "entry_ts": "", "ai_yes_prob": 0.6, "edge": 0.1}]
    with patch.object(bot, "get_market", return_value=_market(condition_id="c1", closed=False)):
        resolved = bot._process_resolutions(cfg)
    assert resolved == 0
    assert len(cfg["positions"]) == 1


def test_tick_disabled_skips():
    cfg = bot._DEFAULT
    with patch.object(bot, "_load", return_value=dict(cfg)):
        result = bot.tick()
    assert result == {"skipped": "disabled"}
