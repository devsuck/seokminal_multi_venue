"""카피트레이딩 자동청산 봇(tick) 테스트."""
from unittest.mock import MagicMock, patch

from api_server import copytrade_autobot as bot


def _pos(symbol="AAPL", plpc=0.0, pl_dollar=0.0):
    p = MagicMock()
    p.symbol = symbol
    p.unrealized_plpc = plpc
    p.unrealized_pl = pl_dollar
    return p


def _run(cfg, positions):
    client = MagicMock()
    client.get_all_positions.return_value = positions
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


def test_disabled_skips():
    cfg = {"enabled": False, "tp_pct": 15.0, "sl_pct": 7.0}
    result, client = _run(cfg, [_pos("AAPL", plpc=0.30)])
    assert result == {"skipped": "disabled"}
    client.get_all_positions.assert_not_called()
