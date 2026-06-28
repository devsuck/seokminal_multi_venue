import pytest
from fastapi.testclient import TestClient

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
