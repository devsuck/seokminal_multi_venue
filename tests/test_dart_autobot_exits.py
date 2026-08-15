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
    # 당일 손절 지정가 주문이 먼저 걸리고(entry*(1-0.07)=930), TP 도달 시 그걸 취소한 뒤 시장가 매도.
    kis.place_order.assert_any_call("005930", "SELL", 10, "LIMIT", price=930)
    kis.place_order.assert_any_call("005930", "SELL", 10, "MARKET")
    assert kis.place_order.call_count == 2
    kis.cancel_order.assert_called_once()
    assert cfg["positions"] == []
    assert cfg["spent"] == 0.0  # 원금 10*1000 회수


def test_sl_order_placed_once_per_day_not_replaced_next_tick():
    pos = _pos(entry=1000.0, qty=10)
    cfg = _cfg([pos], spent=10000.0)
    sold, kis = _run(cfg, price=1050.0)  # 규칙 미충족 — 보유 유지
    assert sold == 0
    kis.place_order.assert_called_once_with("005930", "SELL", 10, "LIMIT", price=930)
    assert cfg["positions"][0]["sl_order_date"] == bot._kst_today_str()

    # 같은 날 다음 tick — 이미 당일 상신됐으니 재상신 안 함.
    kis2 = MagicMock()
    with patch.object(bot, "_current_price", return_value=1050.0), \
         patch.object(bot, "_kis", return_value=kis2), \
         patch.object(bot, "_log_event"):
        bot._process_exits(cfg)
    kis2.place_order.assert_not_called()


def test_sl_triggers_sell():
    cfg = _cfg([_pos(entry=1000.0)])
    sold, _ = _run(cfg, price=900.0)  # -10% < SL -7%
    assert sold == 1


def test_sl_uses_queried_fill_price_when_available():
    cfg = _cfg([_pos(entry=1000.0, qty=10)], spent=10000.0)
    kis = MagicMock()
    kis.get_order_status.return_value = {"status": "FILLED", "filled": 10.0, "remaining": 0.0, "avg_price": 935.0}
    log = MagicMock()
    with patch.object(bot, "_current_price", return_value=900.0), \
         patch.object(bot, "_kis", return_value=kis), \
         patch.object(bot, "_log_event", log):
        sold = bot._process_exits(cfg)
    assert sold == 1
    sell_events = [c.args[0] for c in log.call_args_list if c.args[0]["kind"] == "sell"]
    assert len(sell_events) == 1
    assert sell_events[0]["exit_price"] == 935.0  # 지정가(930) 근사 아니라 실제 체결 평균가
    assert sell_events[0]["pnl_pct"] == round((935.0 - 1000.0) / 1000.0 * 100, 2)


def test_stale_position_after_sl_fill_logs_accurate_sell_via_fill_query():
    cfg = _cfg([_pos(entry=1000.0, qty=10)], spent=10000.0)
    kis = MagicMock()
    kis.get_order_status.return_value = {"status": "FILLED", "filled": 10.0, "remaining": 0.0, "avg_price": 928.0}

    def place_order_side_effect(code, side, qty, division, price=None):
        if division == "MARKET":
            raise RuntimeError("KIS API error rt_cd=1: 모의투자 잔고내역이 없습니다.")
        return {"order_id": "ORD1"}
    kis.place_order.side_effect = place_order_side_effect
    log = MagicMock()
    # TP 조건(가격 1300)으로 시장가 매도 시도 → 이미 손절 지정가로 선체결돼 잔고 없음 →
    # 체결가 조회로 정확한 손절 로그 남겨야 함(TP가 아니라 실제로 체결된 SL로 기록).
    with patch.object(bot, "_current_price", return_value=1300.0), \
         patch.object(bot, "_kis", return_value=kis), \
         patch.object(bot, "_log_event", log):
        sold = bot._process_exits(cfg)
    assert sold == 1
    assert cfg["positions"] == []
    assert cfg["spent"] == 0.0
    sell_events = [c.args[0] for c in log.call_args_list if c.args[0]["kind"] == "sell"]
    assert len(sell_events) == 1
    assert sell_events[0]["exit_price"] == 928.0


def test_max_hold_days_triggers_sell():
    cfg = _cfg([_pos(entry=1000.0, days_ago=25)], max_days=20)
    sold, _ = _run(cfg, price=1010.0)  # 수익률은 중립이지만 25일 보유
    assert sold == 1


def test_within_rules_keeps_position():
    cfg = _cfg([_pos(entry=1000.0, days_ago=3)])
    sold, kis = _run(cfg, price=1050.0)  # +5%, 3일 — 규칙 미충족
    assert sold == 0
    # 자체 규칙 미충족이라도 당일 손절 지정가 주문은 걸림 — 시장가 매도만 안 나감.
    kis.place_order.assert_called_once_with("005930", "SELL", 10, "LIMIT", price=930)
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


def test_sell_no_holdings_drops_stale_position():
    cfg = _cfg([_pos(entry=1000.0)], spent=10000.0)
    kis = MagicMock()
    kis.place_order.side_effect = RuntimeError("KIS API error rt_cd=1: 모의투자 잔고내역이 없습니다.")
    with patch.object(bot, "_current_price", return_value=1300.0), \
         patch.object(bot, "_kis", return_value=kis), \
         patch.object(bot, "_log_event"):
        sold = bot._process_exits(cfg)
    assert sold == 0
    assert cfg["positions"] == []   # 브로커에 실보유 없음 → 드롭, 재시도 안 함
    assert cfg["spent"] == 10000.0  # 이미 예전에 정산된 것으로 간주 — 중복 차감 없음
