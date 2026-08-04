"""Alpaca 데이터 헬퍼 — vrp_bot/main.py의 IB→Alpaca 데이터 교체가 의존하는 파싱 로직."""
from unittest.mock import MagicMock, patch

from api_server.routers import alpaca_shared as shared


class _Quote:
    def __init__(self, bid, ask):
        self.bid_price = bid
        self.ask_price = ask


class _Greeks:
    def __init__(self, delta):
        self.delta = delta


class _Snap:
    def __init__(self, iv, delta, bid, ask):
        self.implied_volatility = iv
        self.greeks = _Greeks(delta) if delta is not None else None
        self.latest_quote = _Quote(bid, ask) if bid is not None else None


def test_fetch_option_chain_parses_occ_symbols_into_expiry_groups():
    fake_client = MagicMock()
    fake_client.get_option_chain.return_value = {
        "AAPL260119C00150000": _Snap(0.25, 0.42, 1.1, 1.3),
        "AAPL260119P00140000": _Snap(0.30, -0.18, 0.9, 1.0),
        "AAPL260220C00150000": _Snap(0.22, 0.40, 1.5, 1.7),
        "GARBAGE": _Snap(0.1, 0.1, 0.1, 0.1),  # OCC 파싱 실패 → 무시
    }
    with patch.object(shared, "_option_data_client", return_value=fake_client):
        chain = shared._fetch_option_chain("AAPL", max_expiries=6)

    assert set(chain.keys()) == {"20260119", "20260220"}
    jan = {(r["strike"], r["right"]): r for r in chain["20260119"]}
    assert jan[(150.0, "C")]["delta"] == 0.42
    assert jan[(150.0, "C")]["bid"] == 1.1
    assert jan[(150.0, "C")]["ask"] == 1.3
    assert jan[(140.0, "P")]["iv"] == 0.30


def test_fetch_option_chain_caps_to_max_expiries_closest_first():
    fake_client = MagicMock()
    fake_client.get_option_chain.return_value = {
        f"AAPL{d}C00150000": _Snap(0.2, 0.4, 1.0, 1.1)
        for d in ("260119", "260220", "260320")
    }
    with patch.object(shared, "_option_data_client", return_value=fake_client):
        chain = shared._fetch_option_chain("AAPL", max_expiries=2)
    assert sorted(chain.keys()) == ["20260119", "20260220"]


def test_fetch_daily_closes_extracts_close_prices_in_order():
    # BarSet엔 제대로 된 __contains__/__getitem__이 없어(`sym in resp`가 항상 False)
    # .data dict로 직접 조회해야 함 — 이 계약을 고정하기 위해 응답을 진짜 dict가 아닌
    # `.data`만 있는 객체로 흉내낸다.
    fake_bar = lambda c: MagicMock(close=c)
    fake_resp = MagicMock(data={"AAPL": [fake_bar(100.0), fake_bar(101.5)]})
    fake_resp.__contains__ = MagicMock(return_value=False)
    fake_client = MagicMock()
    fake_client.get_stock_bars.return_value = fake_resp
    with patch.object(shared, "_data_client", return_value=fake_client):
        closes = shared._fetch_daily_closes("aapl", days=30)
    assert closes == [100.0, 101.5]
