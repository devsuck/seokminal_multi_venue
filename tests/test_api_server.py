import datetime as dt

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from api_server.main import app

client = TestClient(app)


def test_bars_happy_path_returns_known_instrument_data():
    response = client.get(
        "/bars",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["instrument_id"] == "AAPL.NASDAQ"
    assert len(body["bars"]) > 0
    first_bar = body["bars"][0]
    assert set(first_bar.keys()) == {
        "ts_event",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }


def test_bars_unknown_instrument_returns_400():
    response = client.get(
        "/bars",
        params={
            "instrument_id": "NOPE.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 400


def test_backtest_happy_path_returns_all_metric_keys():
    response = client.get(
        "/backtest",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
            "strategy": "ema_cross",
            "fast": 10,
            "slow": 20,
        },
    )
    assert response.status_code == 200
    body = response.json()
    # BacktestResponse(api_server/main.py) 필드 전체 — sortino/beta/volatility/
    # win_rate/profit_loss_ratio/avg_win/avg_loss/trades 는 리스크 대시보드
    # 단계에서 추가됐으나 이 스모크 테스트는 최초 5개 키에서 갱신 안 돼있었음.
    assert set(body.keys()) == {
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "volatility",
        "beta",
        "total_pnl",
        "total_pnl_pct",
        "win_rate",
        "profit_loss_ratio",
        "avg_win",
        "avg_loss",
        "bar_count",
        "trades",
    }


def test_backtest_unsupported_strategy_returns_400():
    response = client.get(
        "/backtest",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
            "strategy": "not_a_real_strategy",
            "fast": 10,
            "slow": 20,
        },
    )
    assert response.status_code == 400


def test_correlation_happy_path_returns_known_pair_value():
    response = client.get(
        "/correlation",
        params={
            "instrument_ids": "005930.XKRX,000660.XKRX",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 200
    body = response.json()
    pairs = {(p["a"], p["b"]): p["correlation"] for p in body["pairs"]}
    assert 0.5 < pairs[("005930.XKRX", "000660.XKRX")] < 0.9


def test_correlation_single_instrument_returns_400():
    response = client.get(
        "/correlation",
        params={
            "instrument_ids": "005930.XKRX",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 400


# ── Options endpoints ─────────────────────────────────────────────────────────

def test_options_greeks_call():
    """GET /options/greeks returns delta/gamma/theta/vega/rho/price."""
    r = client.get("/options/greeks?option_type=call&spot=100&strike=100&expiry_days=30&rate=0.05&vol=0.2")
    assert r.status_code == 200
    data = r.json()
    assert 0 < data["delta"] < 1
    assert data["gamma"] > 0
    assert data["price"] > 0


def test_options_greeks_put():
    """GET /options/greeks returns negative delta for put."""
    r = client.get("/options/greeks?option_type=put&spot=100&strike=100&expiry_days=30&rate=0.05&vol=0.2")
    assert r.status_code == 200
    data = r.json()
    assert -1 < data["delta"] < 0


def test_options_chain_structure():
    """GET /options/chain returns list with required keys."""
    r = client.get("/options/chain?spot=100&expiry_days=30&rate=0.05&vol=0.2")
    assert r.status_code == 200
    data = r.json()
    assert "rows" in data
    assert len(data["rows"]) > 0
    row = data["rows"][0]
    assert "strike" in row and "call_price" in row and "put_price" in row


def test_options_iv_surface_shape():
    """GET /options/iv-surface returns 9x7 grid."""
    r = client.get("/options/iv-surface?spot=100&rate=0.05&atm_vol=0.2")
    assert r.status_code == 200
    data = r.json()
    assert len(data["strikes"]) == 9
    assert len(data["expiry_days"]) == 7
    assert len(data["iv_surface"]) == 9
    assert len(data["iv_surface"][0]) == 7


# ── Futures endpoints ─────────────────────────────────────────────────────────

def test_futures_price_contango():
    """GET /futures/price returns contango when r > q."""
    r = client.get("/futures/price?spot=100&rate=0.05&convenience_yield=0.02&expiry_days=30")
    assert r.status_code == 200
    data = r.json()
    assert data["price"] > 100
    assert data["market_structure"] == "contango"


def test_futures_calendar_structure():
    """GET /futures/calendar returns 7 rows with required keys."""
    r = client.get("/futures/calendar?spot=100&rate=0.05&convenience_yield=0.02")
    assert r.status_code == 200
    data = r.json()
    assert "rows" in data
    assert len(data["rows"]) == 7
    row = data["rows"][0]
    assert "expiry_days" in row and "price" in row and "market_structure" in row


def test_futures_roll_structure():
    """GET /futures/roll returns list of rolls with required keys."""
    r = client.get("/futures/roll?spot=100&rate=0.05&convenience_yield=0.02&front_days=30")
    assert r.status_code == 200
    data = r.json()
    assert "rolls" in data
    assert len(data["rolls"]) == 5
    roll = data["rolls"][0]
    assert "roll_cost" in roll and "annualized_roll_yield" in roll


# ── Forex endpoints ───────────────────────────────────────────────────────────

def test_forex_forward_premium():
    """GET /forex/forward returns premium when r_domestic > r_foreign."""
    r = client.get("/forex/forward?spot=1.10&rate_domestic=0.05&rate_foreign=0.03&days=90")
    assert r.status_code == 200
    data = r.json()
    assert data["forward"] > 1.10
    assert data["market_structure"] == "premium"


def test_forex_curve_structure():
    """GET /forex/curve returns 6 rows with required keys."""
    r = client.get("/forex/curve?spot=1.10&rate_domestic=0.05&rate_foreign=0.03")
    assert r.status_code == 200
    data = r.json()
    assert "rows" in data
    assert len(data["rows"]) == 6
    row = data["rows"][0]
    assert "tenor_days" in row and "forward" in row and "market_structure" in row


def test_forex_carry_structure():
    """GET /forex/carry returns carry analysis with required keys."""
    r = client.get("/forex/carry?spot=1.10&rate_domestic=0.05&rate_foreign=0.03&days=365")
    assert r.status_code == 200
    data = r.json()
    assert "carry_rate" in data and "favorable" in data and "forward" in data
    assert data["favorable"] is True


# ── Crypto (Hyperliquid) endpoints ────────────────────────────────────────────

MOCK_HL_MIDS = {"BTC": "94500.0", "ETH": "3200.0"}

MOCK_HL_META = [
    {"name": "BTC", "szDecimals": 5, "maxLeverage": 50},
    {"name": "ETH", "szDecimals": 4, "maxLeverage": 25},
]

MOCK_HL_CTXS = [
    {
        "funding": "0.0001",
        "openInterest": "5000.0",
        "prevDayPx": "93000.0",
        "dayNtlVlm": "500000000.0",
        "markPx": "94500.0",
        "midPx": "94500.0",
    },
    {
        "funding": "-0.00005",
        "openInterest": "20000.0",
        "prevDayPx": "3100.0",
        "dayNtlVlm": "200000000.0",
        "markPx": "3200.0",
        "midPx": "3200.0",
    },
]

MOCK_HL_CANDLES = [
    {
        "t": 1700000000000, "T": 1700086399000, "s": "BTC", "i": "1d",
        "o": "93000.0", "c": "94500.0", "h": "95000.0", "l": "92000.0",
        "v": "123.45", "n": 5678,
    }
]

MOCK_HL_BOOK = {
    "coin": "BTC",
    "time": 1700000000000,
    "levels": [
        [{"px": "94490.0", "sz": "0.5", "n": 3}, {"px": "94480.0", "sz": "1.0", "n": 5}],
        [{"px": "94510.0", "sz": "0.3", "n": 2}, {"px": "94520.0", "sz": "0.8", "n": 4}],
    ],
}


@patch("api_server.main.get_meta_and_ctxs")
def test_crypto_assets_structure(mock_meta_ctxs):
    mock_meta_ctxs.return_value = (MOCK_HL_META, MOCK_HL_CTXS)
    r = client.get("/crypto/assets")
    assert r.status_code == 200
    data = r.json()
    assert "assets" in data and data["count"] == 2
    asset = data["assets"][0]
    assert asset["name"] == "BTC"
    assert "mid_price" in asset and "funding_rate_8h" in asset and "day_change_pct" in asset


@patch("api_server.main.get_candles")
def test_crypto_candles_structure(mock_candles):
    mock_candles.return_value = MOCK_HL_CANDLES
    r = client.get("/crypto/candles?coin=BTC&interval=1d&days=30")
    assert r.status_code == 200
    data = r.json()
    assert data["coin"] == "BTC" and data["interval"] == "1d"
    assert len(data["candles"]) == 1
    candle = data["candles"][0]
    assert "time_ms" in candle and "open" in candle and "close" in candle


@patch("api_server.main.get_l2_book")
def test_crypto_book_structure(mock_book):
    mock_book.return_value = MOCK_HL_BOOK
    r = client.get("/crypto/book?coin=BTC")
    assert r.status_code == 200
    data = r.json()
    assert "bids" in data and "asks" in data and "mid_price" in data and "spread" in data
    assert data["bids"][0]["price"] == pytest.approx(94490.0)
    assert data["asks"][0]["price"] == pytest.approx(94510.0)


# ── IB bars endpoint ─────────────────────────────────────────────────────────

from unittest.mock import AsyncMock, MagicMock


def _make_mock_ib_bar(date_str="20250102"):
    bar = MagicMock()
    bar.date = date_str
    bar.open = 150.0
    bar.high = 155.0
    bar.low = 148.0
    bar.close = 152.0
    bar.volume = 1_000_000.0
    return bar


def test_ib_bars_stock_structure():
    # 주식 브랜치는 IB Gateway 상시가동 문제로 Alpaca(_fetch_stock_bars)로 교체됨(2026-08-04).
    bar = MagicMock()
    bar.date = dt.datetime(2025, 1, 2, tzinfo=dt.timezone.utc)
    bar.open, bar.high, bar.low, bar.close, bar.volume = 150.0, 155.0, 148.0, 152.0, 1_000_000.0
    with patch("api_server.routers.alpaca_shared._fetch_stock_bars", return_value=[bar]):
        r = client.get("/ib/bars?symbol=AAPL&asset_type=stock")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "AAPL.STOCK"
    assert data["asset_type"] == "stock"
    assert data["count"] == 1
    bar_out = data["bars"][0]
    assert "ts_ms" in bar_out and "open" in bar_out and "close" in bar_out


@patch("api_server.main.IBClient")
def test_ib_bars_forex_structure(mock_cls):
    inst = MagicMock()
    inst.get_daily_bars_forex = AsyncMock(return_value=[_make_mock_ib_bar()])
    inst._ib.isConnected.return_value = False
    mock_cls.return_value = inst
    r = client.get("/ib/bars?symbol=EURUSD&asset_type=forex")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "EURUSD.FOREX"
    assert data["asset_type"] == "forex"


def test_ib_bars_invalid_asset_type_returns_422():
    r = client.get("/ib/bars?symbol=AAPL&asset_type=bond")
    assert r.status_code == 422


def test_ib_bars_ib_error_returns_400():
    with patch("api_server.routers.alpaca_shared._fetch_stock_bars",
               side_effect=ValueError("no bars returned for FAKE")):
        r = client.get("/ib/bars?symbol=FAKE&asset_type=stock")
    assert r.status_code == 400


@patch("api_server.main.IBClient")
def test_ib_bars_future_structure(mock_cls):
    inst = MagicMock()
    inst.get_daily_bars_future = AsyncMock(return_value=[_make_mock_ib_bar()])
    inst._ib.isConnected.return_value = False
    mock_cls.return_value = inst
    r = client.get("/ib/bars?symbol=ES&asset_type=future&exchange=CME&expiry=202509")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "ES.CME.FUTURE"
    assert data["asset_type"] == "future"


@patch("api_server.main.IBClient")
def test_ib_bars_option_structure(mock_cls):
    inst = MagicMock()
    inst.get_daily_bars_option = AsyncMock(return_value=[_make_mock_ib_bar()])
    inst._ib.isConnected.return_value = False
    mock_cls.return_value = inst
    r = client.get("/ib/bars?symbol=SPY&asset_type=option&expiry=20270101&strike=500&right=C")
    assert r.status_code == 200
    data = r.json()
    assert "OPTION" in data["symbol"]
    assert data["asset_type"] == "option"


@patch("api_server.main.IBClient")
def test_ib_bars_crypto_structure(mock_cls):
    inst = MagicMock()
    inst.get_daily_bars_crypto = AsyncMock(return_value=[_make_mock_ib_bar()])
    inst._ib.isConnected.return_value = False
    mock_cls.return_value = inst
    r = client.get("/ib/bars?symbol=BTC&asset_type=crypto")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "BTC.CRYPTO"
    assert data["asset_type"] == "crypto"


# ── /search/kr ─────────────────────────────────────────────────────────────────

def test_search_kr_returns_results():
    with patch("api_server.main.search_universe") as mock_search:
        mock_search.return_value = [
            {"code": "005930", "name": "삼성전자", "market": "유가증권"},
            {"code": "006400", "name": "삼성SDI", "market": "유가증권"},
        ]
        r = client.get("/search/kr?q=삼성")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    assert data["results"][0]["code"] == "005930"
    assert data["results"][0]["name"] == "삼성전자"


def test_search_kr_missing_q_returns_422():
    r = client.get("/search/kr")
    assert r.status_code == 422


# ── /kr/bars ───────────────────────────────────────────────────────────────────

def _make_kis_row(date: str = "20250102") -> dict:
    return {
        "stck_bsop_date": date,
        "stck_oprc": "70000",
        "stck_hgpr": "71000",
        "stck_lwpr": "69500",
        "stck_clpr": "70500",
        "acml_vol": "5000000",
    }


@patch("api_server.main.KISClient")
def test_get_kr_bars_structure(mock_cls):
    inst = MagicMock()
    inst.get_daily_price.return_value = [_make_kis_row()]
    mock_cls.return_value = inst
    with patch.dict("os.environ", {"KIS_APP_KEY": "key", "KIS_APP_SECRET": "secret"}):
        r = client.get("/kr/bars?code=005930&days=365")
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == "005930"
    assert len(data["bars"]) == 1
    bar = data["bars"][0]
    assert bar["date"] == "20250102"
    assert bar["open"] == 70000
    assert bar["close"] == 70500
    assert bar["volume"] == 5000000


def test_get_kr_bars_no_credentials_returns_503():
    with patch.dict("os.environ", {"KIS_APP_KEY": "", "KIS_APP_SECRET": ""}):
        r = client.get("/kr/bars?code=005930")
    assert r.status_code == 503


# ── /search/us ─────────────────────────────────────────────────────────────────

@patch("api_server.main.IB")
def test_search_us_structure(mock_ib_cls):
    mock_ib = MagicMock()
    mock_ib.connectAsync = AsyncMock()
    mock_ib.isConnected.return_value = False

    desc = MagicMock()
    desc.contract.symbol = "AAPL"
    desc.contract.description = "Apple Inc"
    desc.contract.secType = "STK"
    desc.contract.primaryExch = "NASDAQ"
    desc.contract.exchange = "SMART"
    desc.contract.currency = "USD"
    mock_ib.reqMatchingSymbolsAsync = AsyncMock(return_value=[desc])
    mock_ib_cls.return_value = mock_ib

    r = client.get("/search/us?q=Apple")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["results"][0]["symbol"] == "AAPL"
    assert data["results"][0]["name"] == "Apple Inc"
    assert data["results"][0]["sec_type"] == "STK"


def test_search_us_missing_q_returns_422():
    r = client.get("/search/us")
    assert r.status_code == 422


# ── _parse_kis_tick ─────────────────────────────────────────────────────────────

from api_server.main import _parse_kis_tick

_SAMPLE_TICK = (
    "0|H0STCNT0|001|"
    "005930^161430^70100^400^5^-0.57^70156^70500^70600^69700^70100^70100^3520^20547350"
)


def test_parse_kis_tick_parses_data():
    result = _parse_kis_tick(_SAMPLE_TICK)
    assert result is not None
    assert result["code"] == "005930"
    assert result["time"] == "161430"
    assert result["price"] == 70100
    assert result["change"] == -400      # sign=5 (down) → negative
    assert result["trade_volume"] == 3520
    assert result["total_volume"] == 20547350


def test_parse_kis_tick_skips_json():
    assert _parse_kis_tick('{"header": {"tr_id": "PINGPONG"}, "body": {}}') is None


def test_parse_kis_tick_skips_wrong_tr_id():
    assert _parse_kis_tick("0|OTHER_TR|001|data^more") is None


# ── WS /ws/live/{code} — credential guard ─────────────────────────────────────

def test_ws_live_no_credentials_sends_error():
    with patch.dict("os.environ", {"KIS_APP_KEY": "", "KIS_APP_SECRET": ""}):
        with client.websocket_connect("/ws/live/005930") as ws:
            data = ws.receive_json()
    assert data.get("error") == "KIS credentials not configured"
