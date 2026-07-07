"""DART 자동매매 매도 로직(_process_exits) 테스트."""
import datetime as dt
from unittest.mock import MagicMock, patch

from api_server import dart_autobot as bot


def _cfg(positions, tp=0.15, sl=0.07, max_days=20, spent=100000.0):
    return {"tp_pct": tp, "sl_pct": sl, "max_hold_days": max_days,
            "spent": spent, "positions": positions}


def _pos(code="005930", qty=10, entry=1000.0, days_ago=1):
    ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)).isoformat()
    return {"code": code, "corp": "테스트", "qty": qty, "entry_price": entry, "entry_ts": ts}


def _run(cfg, price):
    kis = MagicMock()
    with patch.object(bot, "_current_price", return_value=price), \
         patch.object(bot, "_kis", return_value=kis), \
         patch.object(bot, "_log_event"):
        sold = bot._process_exits(cfg)
    return sold, kis


def test_tp_triggers_sell_and_refunds_budget():
    cfg = _cfg([_pos(entry=1000.0, qty=10)], spent=10000.0)
    sold, kis = _run(cfg, price=1200.0)  # +20% > TP 15%
    assert sold == 1
    kis.place_order.assert_called_once_with("005930", "SELL", 10, "MARKET")
    assert cfg["positions"] == []
    assert cfg["spent"] == 0.0  # 원금 10*1000 회수


def test_sl_triggers_sell():
    cfg = _cfg([_pos(entry=1000.0)])
    sold, _ = _run(cfg, price=900.0)  # -10% < SL -7%
    assert sold == 1


def test_max_hold_days_triggers_sell():
    cfg = _cfg([_pos(entry=1000.0, days_ago=25)], max_days=20)
    sold, _ = _run(cfg, price=1010.0)  # 수익률은 중립이지만 25일 보유
    assert sold == 1


def test_within_rules_keeps_position():
    cfg = _cfg([_pos(entry=1000.0, days_ago=3)])
    sold, kis = _run(cfg, price=1050.0)  # +5%, 3일 — 규칙 미충족
    assert sold == 0
    kis.place_order.assert_not_called()
    assert len(cfg["positions"]) == 1


def test_price_fetch_failure_keeps_position():
    cfg = _cfg([_pos()])
    kis = MagicMock()
    with patch.object(bot, "_current_price", return_value=None), \
         patch.object(bot, "_kis", return_value=kis), \
         patch.object(bot, "_log_event"):
        sold = bot._process_exits(cfg)
    assert sold == 0
    assert len(cfg["positions"]) == 1


def test_sell_order_failure_keeps_position():
    cfg = _cfg([_pos(entry=1000.0)], spent=10000.0)
    kis = MagicMock()
    kis.place_order.side_effect = RuntimeError("KIS down")
    with patch.object(bot, "_current_price", return_value=1300.0), \
         patch.object(bot, "_kis", return_value=kis), \
         patch.object(bot, "_log_event"):
        sold = bot._process_exits(cfg)
    assert sold == 0
    assert len(cfg["positions"]) == 1  # 실패 → 보유 유지, 다음 tick 재시도
    assert cfg["spent"] == 10000.0     # 예산도 그대로
