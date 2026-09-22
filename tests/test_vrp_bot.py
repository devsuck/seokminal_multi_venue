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
        self._next_order_id = 1000

    async def place_option_order(self, symbol, expiry, strike, right, side, qty,
                                  order_type, limit_price, wait_fill=False):
        self.calls.append((strike, right, side, qty))
        fill = self.fills.get((strike, right, side))
        self._next_order_id += 1
        status = "Filled" if fill is not None else "Cancelled"
        return {"order_id": self._next_order_id, "status": status,
                "filled": qty if fill is not None else 0, "remaining": 0 if fill is not None else qty,
                "avg_fill_price": fill}

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


def test_scan_and_enter_records_each_leg_to_oms_and_order_audit(tmp_path, monkeypatch):
    """회귀: Fork C Finding 5 — 이 봇은 broker_bridge를 안 거치고 IBOrderClient를
    직접 호출함. dashboard 실현손익/오더뷰가 읽는 api_server.oms·order_audit에
    직접 기록 안 하면 콘도어 4레그 체결이 전부 안 보임."""
    from api_server import oms
    monkeypatch.setattr(oms, "_orders", {})
    monkeypatch.setenv("ORDER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))

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

    us_ib_orders = oms.list_orders(venue="US_IB")
    assert len(us_ib_orders) == 4
    assert all(o["symbol"].startswith("SPY_") for o in us_ib_orders)
    assert len({o["symbol"] for o in us_ib_orders}) == 4  # 4개 레그가 별개 계약으로 기록되어야 함(회귀: FIFO PnL 매처가 종목코드로만 매칭 — bare "SPY"였으면 롱/숏 4레그가 한 종목으로 뭉쳐 서로 매칭됨)
    assert all(o["status"] == "FILLED" for o in us_ib_orders)

    from api_server.order_audit import read_recent
    entries = read_recent(path=tmp_path / "audit.jsonl")
    assert len(entries) == 4
    assert all(e["venue"] == "US_IB" for e in entries)


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


def test_tick_kill_switch_blocks_new_entries_but_not_exits():
    """킬스위치는 신규 진입(_scan_and_enter)만 막아야 함 — 만기 청산/손절까지
    막으면 드로다운 브레이크가 오히려 위험을 방치하게 됨(회귀: Fork C Finding 4)."""
    expiry = _expiry(35)
    pos = _position(expiry)
    cfg = _cfg(profit_target_pct=0.5, stop_multiple=2.0, exit_dte=7)
    cfg["positions"] = [pos]
    cfg["spent"] = pos["max_loss"]
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
    with patch.object(bot, "_load", return_value=cfg), \
         patch.object(bot, "_save"), \
         patch.object(bot, "_data_client", return_value=FakeDataClient(_CLOSES, cheap_chain)), \
         patch.object(bot, "_order_client", return_value=FakeOrderClient(fills)), \
         patch.object(bot, "_log_event"), \
         patch.object(bot, "_scan_and_enter") as mock_enter, \
         patch("api_server.risk_state.is_killed", return_value=True):
        result = await_run(bot.tick())
    mock_enter.assert_not_called()  # 신규 진입은 막힘
    assert result == {"skipped": "kill_switch", "closed": 1}
    assert cfg["positions"] == []  # 청산은 킬스위치와 무관하게 실행됨
    assert cfg["realized_pnl"] > 0


def test_tick_concurrent_calls_are_serialized():
    """백그라운드 루프와 수동 /run-now가 같은 이벤트루프에서 겹쳐 돌면 await
    지점에서 인터리빙돼 cfg 로드→수정→저장이 경합할 수 있음 — asyncio.Lock이
    tick() 전체를 직렬화해야 함(회귀: Fork C Finding 1)."""
    import asyncio
    order = []

    async def _slow_impl():
        order.append("start")
        await asyncio.sleep(0.05)
        order.append("end")
        return {"ok": True}

    async def _run_both():
        with patch.object(bot, "_tick_impl", side_effect=_slow_impl):
            await asyncio.gather(bot.tick(), bot.tick())

    await_run(_run_both())
    assert order == ["start", "end", "start", "end"]


def await_run(coro):
    import asyncio
    return asyncio.new_event_loop().run_until_complete(coro)
