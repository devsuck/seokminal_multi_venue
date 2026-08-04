"""통합 손익 대시보드(/dashboard/pnl/all) — council 에이전트 + 5개 독립봇 합산."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api_server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    return TestClient(app)


def test_dashboard_pnl_all_sums_agents_and_bots(client):
    with patch("api_server.main._dart_bot_status", return_value={}), \
         patch("api_server.main._vrp_bot_status", return_value={"realized_pnl": 100.0}), \
         patch("api_server.main._polymarket_bot_status", return_value={"realized_pnl": -50.0}), \
         patch("api_server.main._sharp_wallet_bot_status", return_value={"realized_pnl": 25.0}), \
         patch("api_server.main._copytrade_bot_status", return_value={"realized_pnl": 10.0}):
        r = client.get("/dashboard/pnl/all")
    assert r.status_code == 200
    body = r.json()
    assert body["bots_totals"]["realized_pnl"] == 85.0  # 100-50+25+10
    dart = next(b for b in body["bots"] if b["id"] == "dart_autobot")
    assert dart["realized_pnl"] is None  # 미추적 — 합산에서 제외됨
    assert body["grand_total_realized_pnl"] == body["agents_totals"]["realized_pnl"] + 85.0
    assert "agents" in body and isinstance(body["agents"], list)
