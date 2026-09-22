"""카피트레이딩 자동청산 봇(tick) 테스트."""
import threading
import time
from unittest.mock import MagicMock, patch

from api_server import copytrade_autobot as bot


def _pos(symbol="AAPL", plpc=0.0, pl_dollar=0.0):
    p = MagicMock()
    p.symbol = symbol
    p.unrealized_plpc = plpc
    p.unrealized_pl = pl_dollar
    return p


def _fake_order(symbol="AAPL"):
    o = MagicMock()
    o.id = "ord-1"
    o.symbol = symbol
    o.side = MagicMock(value="sell")
    o.qty = 10.0
    o.filled_qty = 10.0
    o.status = MagicMock(value="filled")
    o.filled_avg_price = 155.0
    o.created_at = None
    return o


def _run(cfg, positions, close_return=None):
    client = MagicMock()
    client.get_all_positions.return_value = positions
    client.close_position.return_value = close_return if close_return is not None else _fake_order()
    with patch.object(bot, "_load", return_value=cfg), \
         patch.object(bot, "_save"), \
         patch.object(bot, "_log_event"), \
         patch.dict("os.environ", {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"}), \
         patch("alpaca.trading.client.TradingClient", return_value=client):
        return bot.tick(), client


def test_tp_closes_position():
    cfg = {"enabled": True, "tp_pct": 15.0, "sl_pct": 7.0}
    result, client = _run(cfg, [_pos("AAPL", plpc=0.20)])  # +20% > TP 15%
    assert result["count"] == 1
    client.close_position.assert_called_once_with("AAPL")


def test_sl_closes_position():
    cfg = {"enabled": True, "tp_pct": 15.0, "sl_pct": 7.0}
    result, client = _run(cfg, [_pos("AAPL", plpc=-0.10)])  # -10% < -SL 7%
    assert result["count"] == 1
    client.close_position.assert_called_once_with("AAPL")


def test_within_rules_keeps_position():
    cfg = {"enabled": True, "tp_pct": 15.0, "sl_pct": 7.0}
    result, client = _run(cfg, [_pos("AAPL", plpc=0.05)])  # +5% — 규칙 미충족
    assert result["count"] == 0
    client.close_position.assert_not_called()


def test_tp_close_accumulates_realized_pnl_dollar():
    cfg = {"enabled": True, "tp_pct": 15.0, "sl_pct": 7.0, "realized_pnl": 100.0}
    result, client = _run(cfg, [_pos("AAPL", plpc=0.20, pl_dollar=250.0)])
    assert result["closed"][0]["pl_dollar"] == 250.0
    assert cfg["realized_pnl"] == 350.0  # 기존 100 + 이번 청산 250


def test_kill_switch_does_not_block_autoliquidation():
    """이 봇은 신규 매수 없이 TP/SL 자동청산만 함 — 킬스위치가 이 유일한 기능을
    막으면 드로다운 브레이크가 위험 축소 자체를 정지시키는 역설이 됨(회귀:
    Fork C Finding 4)."""
    cfg = {"enabled": True, "tp_pct": 15.0, "sl_pct": 7.0}
    with patch("api_server.risk_state.is_killed", return_value=True):
        result, client = _run(cfg, [_pos("AAPL", plpc=0.20)])  # +20% > TP 15%
    assert result["count"] == 1
    client.close_position.assert_called_once_with("AAPL")


def test_liquidation_recorded_to_oms_and_order_audit(tmp_path, monkeypatch):
    """회귀: Fork C Finding 5 — close_position()은 broker_bridge를 안 거치고
    Alpaca TradingClient를 직접 호출함. dashboard 실현손익/오더뷰가 읽는
    api_server.oms·order_audit에 직접 기록 안 하면 자동청산이 안 보임."""
    from api_server import oms
    monkeypatch.setattr(oms, "_orders", {})
    monkeypatch.setenv("ORDER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))

    cfg = {"enabled": True, "tp_pct": 15.0, "sl_pct": 7.0}
    result, client = _run(cfg, [_pos("AAPL", plpc=0.20)])
    assert result["count"] == 1

    recorded = oms.get_order("US_ALPACA", "ord-1")
    assert recorded is not None
    assert recorded["symbol"] == "AAPL"
    assert recorded["status"] == "FILLED"

    from api_server.order_audit import read_recent
    entries = read_recent(path=tmp_path / "audit.jsonl")
    assert len(entries) == 1
    assert entries[0]["venue"] == "US_ALPACA"


def test_tick_concurrent_calls_are_serialized():
    """회귀: Fork C Finding 1 — 전역 락이 tick() 전체를 직렬화해야 함."""
    order = []

    def _slow_impl():
        order.append("start")
        time.sleep(0.05)
        order.append("end")
        return {"ok": True}

    with patch.object(bot, "_tick_impl", side_effect=_slow_impl):
        t1 = threading.Thread(target=bot.tick)
        t2 = threading.Thread(target=bot.tick)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    assert order == ["start", "end", "start", "end"]


def test_disabled_skips():
    cfg = {"enabled": False, "tp_pct": 15.0, "sl_pct": 7.0}
    result, client = _run(cfg, [_pos("AAPL", plpc=0.30)])
    assert result == {"skipped": "disabled"}
    client.get_all_positions.assert_not_called()
