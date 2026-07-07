"""Insider trading endpoint tests (mocked external APIs)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app)


# ── OpenDART / KR ──────────────────────────────────────────────────────────────

def test_insider_kr_search_ok():
    mock_rows = [
        {"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930"},
    ]
    with patch("api_server.main._dart_search", return_value=mock_rows):
        r = client.get("/insider/kr/search", params={"q": "삼성전자"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["corp_code"] == "00126380"
    assert data[0]["corp_name"] == "삼성전자"


def test_insider_kr_trades_ok():
    mock_rows = [
        {
            "rcept_dt": "20240315",
            "reporter": "이재용",
            "trade_type": "BUY",
            "shares_change": 50000,
            "shares_total": 5000000,
            "ownership_pct": 1.55,
            "report_type": "변동",
            "corp_name": "삼성전자",
        }
    ]
    with patch("api_server.main._dart_trades", return_value=mock_rows):
        r = client.get("/insider/kr", params={"corp_code": "00126380", "days": 90})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["trade_type"] == "BUY"
    assert data[0]["reporter"] == "이재용"
    assert data[0]["shares_change"] == 50000


def test_insider_kr_empty():
    with patch("api_server.main._dart_trades", return_value=[]):
        r = client.get("/insider/kr", params={"corp_code": "99999999", "days": 30})
    assert r.status_code == 200
    assert r.json() == []


def test_insider_kr_search_api_error():
    with patch("api_server.main._dart_search", side_effect=ValueError("OPENDART_API_KEY not set")):
        r = client.get("/insider/kr/search", params={"q": "삼성"})
    assert r.status_code == 503


# ── US 내부자 (Finnhub 우선 + SEC EDGAR 폴백) ─────────────────────────────────

_US_MOCK_ROWS = [
    {
        "filing_date": "2024-03-10",
        "transaction_date": "2024-03-08",
        "reporter": "Tim Cook",
        "ticker": "AAPL",
        "issuer": "Apple Inc",
        "transaction_code": "S",
        "trade_type": "SELL",
        "shares": 250000.0,
        "price_per_share": 172.50,
        "value_usd": 43125000.0,
        "shares_owned_after": 3200000.0,
    }
]


def test_insider_us_finnhub_primary():
    """Finnhub이 데이터 주면 EDGAR 안 감."""
    with patch("insider.finnhub_client.get_insider_transactions", return_value=_US_MOCK_ROWS), \
         patch("api_server.main._edgar_trades", side_effect=AssertionError("EDGAR 호출되면 안 됨")):
        r = client.get("/insider/us", params={"ticker": "AAPL", "days": 90})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["trade_type"] == "SELL"
    assert data[0]["reporter"] == "Tim Cook"
    assert data[0]["value_usd"] == pytest.approx(43125000.0)


def test_insider_us_edgar_fallback():
    """Finnhub 실패 시 EDGAR 폴백."""
    with patch("insider.finnhub_client.get_insider_transactions", side_effect=RuntimeError("finnhub down")), \
         patch("api_server.main._edgar_trades", return_value=_US_MOCK_ROWS):
        r = client.get("/insider/us", params={"ticker": "AAPL", "days": 90})
    assert r.status_code == 200
    assert r.json()[0]["reporter"] == "Tim Cook"


def test_insider_us_not_found():
    with patch("insider.finnhub_client.get_insider_transactions", return_value=[]), \
         patch("api_server.main._edgar_trades", return_value=[]):
        r = client.get("/insider/us", params={"ticker": "XXXXXX", "days": 90})
    assert r.status_code == 404


def test_insider_us_both_sources_error():
    with patch("insider.finnhub_client.get_insider_transactions", side_effect=RuntimeError("finnhub down")), \
         patch("api_server.main._edgar_trades", side_effect=RuntimeError("network error")):
        r = client.get("/insider/us", params={"ticker": "AAPL", "days": 30})
    assert r.status_code == 502
