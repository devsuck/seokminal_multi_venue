"""VRP 아이언 콘도어 봇 테스트 (IB 클라이언트는 페이크로 대체)."""
import datetime as dt
from unittest.mock import patch

from api_server import vrp_bot as bot


class FakeBar:
    def __init__(self, close):
        self.close = close


class FakeDataClient:
    def __init__(self, closes, chain):
        self._closes = closes
        self._chain = chain

    async def get_daily_bars(self, symbol, end, duration):
        return [FakeBar(c) for c in self._closes]

    async def get_option_chain(self, symbol, max_expiries=6):
        return self._chain


class FakeOrderClient:
    def __init__(self, fills=None):
        self.fills = fills or {}
        self.calls = []

    async def place_option_order(self, symbol, expiry, strike, right, side, qty,
                                  order_type, limit_price, wait_fill=False):
        self.calls.append((strike, right, side, qty))
        fill = self.fills.get((strike, right, side))
        return {"avg_fill_price": fill}

    async def close(self):
        pass


def _cfg(**over):
    return {**bot._DEFAULT, "enabled": True, "positions": [], "symbols": ["SPY"], **over}


def _expiry(days: int) -> str:
    return (dt.date.today() + dt.timedelta(days=days)).strftime("%Y%m%d")


def _build_chain(expiry: str, spot: float = 450.0):
    rows = [
        {"strike": 420, "right": "P", "bid": 0.5, "ask": 0.6, "iv": 0.80, "delta": -0.04},
        {"strike": 430, "right": "P", "bid": 1.0, "ask": 1.2, "iv": 0.80, "delta": -0.08},
        {"strike": 440, "right": "P", "bid": 3.0, "ask": 3.2, "iv": 0.80, "delta": -0.16},
        {"strike": 460, "right": "C", "bid": 3.0, "ask": 3.2, "iv": 0.80, "delta": 0.16},
        {"strike": 470, "right": "C", "bid": 1.0, "ask": 1.2, "iv": 0.80, "delta": 0.08},
        {"strike": 480, "right": "C", "bid": 0.5, "ask": 0.6, "iv": 0.80, "delta": 0.04},
    ]
    return {expiry: rows}


_CLOSES = [450.0, 452.0, 448.0, 453.0, 447.0] * 6  # noisy but low-vol relative to spot


def test_pick_expiry_selects_within_dte_window_closest_to_mid():
    chain = {
        _expiry(10): [], _expiry(35): [], _expiry(60): [],
    }
    picked = bot._pick_expiry(chain, dte_min=25, dte_max=45)
    assert picked[0] == _expiry(35)


def test_pick_expiry_none_when_nothing_in_window():
    chain = {_expiry(5): [], _expiry(90): []}
    assert bot._pick_expiry(chain, dte_min=25, dte_max=45) is None


def test_pick_wing_call_finds_strike_beyond_width():
    rows = _build_chain("x", 450)["x"]
    wing = bot._pick_wing(rows, "C", short_strike=460, wing=13.5, outward=True)
    assert wing["strike"] == 480  # 470 is only +10 away, short of the 13.5 wing


def test_pick_wing_put_finds_strike_beyond_width():
    rows = _build_chain("x", 450)["x"]
    wing = bot._pick_wing(rows, "P", short_strike=440, wing=13.5, outward=False)
    assert wing["strike"] == 420


def test_scan_and_enter_opens_condor_when_vrp_rich():
    expiry = _expiry(35)
    chain = _build_chain(expiry)
    fills = {
        (420, "P", "BUY"): 0.6, (480, "C", "BUY"): 0.6,
        (440, "P", "SELL"): 3.0, (460, "C", "SELL"): 3.0,
    }
    cfg = _cfg(min_spread_pct=0.15)
    with patch.object(bot, "_data_client", return_value=FakeDataClient(_CLOSES, chain)), \
         patch.object(bot, "_order_client", return_value=FakeOrderClient(fills)), \
         patch.object(bot, "_log_event"):
        entered = await_run(bot._scan_and_enter(cfg))
    assert entered == 1
    pos = cfg["positions"][0]
    assert pos["symbol"] == "SPY"
    assert pos["credit_received"] == round((3.0 + 3.0 - 0.6 - 0.6) * 100, 2)
    assert cfg["spent"] == pos["max_loss"]


def test_scan_and_enter_skips_when_spread_below_threshold():
    expiry = _expiry(35)
    chain = _build_chain(expiry)
    cfg = _cfg(min_spread_pct=50.0)  # 비현실적으로 높은 문턱 — 절대 못 넘음
    with patch.object(bot, "_data_client", return_value=FakeDataClient(_CLOSES, chain)), \
         patch.object(bot, "_order_client", return_value=FakeOrderClient({})), \
         patch.object(bot, "_log_event"):
        entered = await_run(bot._scan_and_enter(cfg))
    assert entered == 0
    assert cfg["positions"] == []


def test_scan_and_enter_skips_when_max_positions_reached():
    cfg = _cfg(max_positions=1)
    cfg["positions"] = [{"symbol": "SPY", "expiry": "x", "legs": [], "credit_received": 1,
                          "max_loss": 1, "entry_ts": "", "entry_vrp_pct": 0}]
    with patch.object(bot, "_data_client") as dc:
        entered = await_run(bot._scan_and_enter(cfg))
    dc.assert_not_called()
    assert entered == 0


def _position(expiry: str):
    return {
        "symbol": "SPY", "expiry": expiry,
        "legs": [
            {"strike": 420, "right": "P", "side": "BUY", "contracts": 1},
            {"strike": 480, "right": "C", "side": "BUY", "contracts": 1},
            {"strike": 440, "right": "P", "side": "SELL", "contracts": 1},
            {"strike": 460, "right": "C", "side": "SELL", "contracts": 1},
        ],
        "credit_received": 480.0, "max_loss": 1520.0,
        "entry_ts": "", "entry_vrp_pct": 100.0,
    }


def test_process_exits_profit_target_closes_position():
    expiry = _expiry(35)
    pos = _position(expiry)
    cfg = _cfg(profit_target_pct=0.5, stop_multiple=2.0, exit_dte=7)
    cfg["positions"] = [pos]
    cfg["spent"] = pos["max_loss"]
    # 대부분 가치를 잃어 되사는 비용이 싸짐 → 크레딧의 큰 %를 확보한 상태로 청산
    cheap_chain = {expiry: [
        {"strike": 420, "right": "P", "bid": 0.05, "ask": 0.1},
        {"strike": 480, "right": "C", "bid": 0.05, "ask": 0.1},
        {"strike": 440, "right": "P", "bid": 0.1, "ask": 0.2},
        {"strike": 460, "right": "C", "bid": 0.1, "ask": 0.2},
    ]}
    fills = {
        (420, "P", "SELL"): 0.05, (480, "C", "SELL"): 0.05,
        (440, "P", "BUY"): 0.2, (460, "C", "BUY"): 0.2,
    }
    with patch.object(bot, "_data_client", return_value=FakeDataClient(_CLOSES, cheap_chain)), \
         patch.object(bot, "_order_client", return_value=FakeOrderClient(fills)), \
         patch.object(bot, "_log_event"):
        closed = await_run(bot._process_exits(cfg))
    assert closed == 1
    assert cfg["positions"] == []
    assert cfg["spent"] == 0.0
    assert cfg["realized_pnl"] > 0


def test_process_exits_dte_exit_forces_close():
    expiry = _expiry(3)  # exit_dte=7 보다 임박
    pos = _position(expiry)
    cfg = _cfg(profit_target_pct=0.99, stop_multiple=99.0, exit_dte=7)
    cfg["positions"] = [pos]
    cfg["spent"] = pos["max_loss"]
    flat_chain = {expiry: [
        {"strike": 420, "right": "P", "bid": 0.5, "ask": 0.6},
        {"strike": 480, "right": "C", "bid": 0.5, "ask": 0.6},
        {"strike": 440, "right": "P", "bid": 3.0, "ask": 3.2},
        {"strike": 460, "right": "C", "bid": 3.0, "ask": 3.2},
    ]}
    fills = {
        (420, "P", "SELL"): 0.5, (480, "C", "SELL"): 0.5,
        (440, "P", "BUY"): 3.2, (460, "C", "BUY"): 3.2,
    }
    with patch.object(bot, "_data_client", return_value=FakeDataClient(_CLOSES, flat_chain)), \
         patch.object(bot, "_order_client", return_value=FakeOrderClient(fills)), \
         patch.object(bot, "_log_event"):
        closed = await_run(bot._process_exits(cfg))
    assert closed == 1  # profit/stop 안 걸려도 DTE 임박이면 강제 청산


def test_process_exits_keeps_position_within_rules():
    expiry = _expiry(35)
    pos = _position(expiry)
    cfg = _cfg(profit_target_pct=0.99, stop_multiple=99.0, exit_dte=7)
    cfg["positions"] = [pos]
    same_chain = {expiry: [
        {"strike": 420, "right": "P", "bid": 0.6, "ask": 0.6},
        {"strike": 480, "right": "C", "bid": 0.6, "ask": 0.6},
        {"strike": 440, "right": "P", "bid": 3.0, "ask": 3.0},
        {"strike": 460, "right": "C", "bid": 3.0, "ask": 3.0},
    ]}
    with patch.object(bot, "_data_client", return_value=FakeDataClient(_CLOSES, same_chain)), \
         patch.object(bot, "_order_client", return_value=FakeOrderClient({})), \
         patch.object(bot, "_log_event"):
        closed = await_run(bot._process_exits(cfg))
    assert closed == 0
    assert len(cfg["positions"]) == 1


def await_run(coro):
    import asyncio
    return asyncio.new_event_loop().run_until_complete(coro)
