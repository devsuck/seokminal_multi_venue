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
    assert set(body.keys()) == {
        "sharpe_ratio",
        "max_drawdown",
        "total_pnl",
        "total_pnl_pct",
        "bar_count",
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
@patch("api_server.main.get_all_mids")
def test_crypto_assets_structure(mock_mids, mock_meta_ctxs):
    mock_mids.return_value = MOCK_HL_MIDS
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
