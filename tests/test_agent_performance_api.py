"""Per-agent performance endpoint (FIFO ledger from cycle fills)."""
import pytest
from fastapi.testclient import TestClient

from api_server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    return TestClient(app)


def _post_fill(client, aid, cycle, symbol, side, qty, price, note=""):
    return client.post(f"/agents/{aid}/cycles", json={
        "cycle": cycle, "decision": side.upper(), "symbol": symbol,
        "note": note, "fill": {"side": side, "qty": qty, "price": price},
    })


def test_performance_missing_agent_404(client):
    assert client.get("/agents/ghost/performance").status_code == 404


def test_performance_no_trades(client):
    aid = client.post("/agents", json={"name": "A", "type": "swing", "account_alloc": 100000}).json()["id"]
    body = client.get(f"/agents/{aid}/performance").json()
    assert body["realized_pnl"] == 0.0
    assert body["trades"] == []
    assert body["open_positions"] == []
    assert body["cash"] == 100000.0


def test_performance_realized_pnl_and_trade_reason(client):
    aid = client.post("/agents", json={"name": "A", "type": "swing", "account_alloc": 100000}).json()["id"]
    _post_fill(client, aid, 1, "AAPL", "buy", 10, 100.0, "저평가 진입")
    _post_fill(client, aid, 2, "AAPL", "sell", 10, 110.0, "목표가 익절")
    body = client.get(f"/agents/{aid}/performance").json()
    assert body["realized_pnl"] == 100.0
    assert body["open_positions"] == []
    # newest-first trade log carries the reason
    assert body["trades"][0]["reason"] == "목표가 익절"
    assert body["trades"][0]["side"] == "sell"
