"""GET /portfolio/* 라우트 테스트 — PortfolioAggregator를 patch로 대체."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import api_server.main as main_module
from api_server.main import app

client = TestClient(app, client=("127.0.0.1", 1))
client.headers["x-api-key"] = main_module._MOBILE_API_KEY  # noqa: SLF001 — 미들웨어가 원격 호스트 취급 시 요구


@patch("jarvis.broker_readonly.aggregator.PortfolioAggregator")
def test_portfolio_summary_returns_aggregator_result(mock_cls):
    mock_inst = mock_cls.return_value
    mock_inst.summary = AsyncMock(return_value={"mode": "live", "total_equity_usd": 1.0,
                                                  "fx_usdkrw": 1350.0, "accounts": [], "holdings": []})
    r = client.get("/portfolio/summary", params={"mode": "live"})
    assert r.status_code == 200
    assert r.json()["total_equity_usd"] == 1.0
    mock_cls.assert_called_once_with("live")


def test_portfolio_summary_rejects_invalid_mode():
    r = client.get("/portfolio/summary", params={"mode": "bogus"})
    assert r.status_code == 422


def test_portfolio_history_returns_empty_when_no_snapshot_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # data/portfolio_snapshots.jsonl 없는 cwd
    r = client.get("/portfolio/history", params={"mode": "live", "days": 30})
    assert r.status_code == 200
    assert r.json() == {"mode": "live", "points": []}


@patch("jarvis.broker_readonly.aggregator.PortfolioAggregator")
def test_portfolio_trades_filters_by_account(mock_cls):
    mock_inst = mock_cls.return_value
    mock_inst.trades.return_value = [{"ts": "t", "venue": "HL", "status": "submitted",
                                        "symbol": "BTC", "side": "BUY", "quantity": 0.1}]
    r = client.get("/portfolio/trades", params={"mode": "live", "account": "hl"})
    assert r.status_code == 200
    assert r.json()["trades"][0]["symbol"] == "BTC"
    mock_inst.trades.assert_called_once_with(account="hl")
