"""Agent management API (create/list/cycles). tmux start/stop not exercised here."""
import pytest
from fastapi.testclient import TestClient

from api_server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # agent_store._db_path() reads AGENT_DB_PATH at call time, so pointing the
    # env at a temp file fully isolates the test — no module reload needed.
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    return TestClient(app)


def test_create_and_list_agent(client):
    r = client.post("/agents", json={"name": "Swing", "type": "swing", "account_alloc": 50000})
    assert r.status_code == 200
    agent = r.json()
    assert agent["type"] == "swing"

    r2 = client.get("/agents")
    body = r2.json()
    assert len(body["agents"]) == 1
    assert "swing" in body["profiles"]
    assert "daytrade" in body["profiles"]


def test_create_rejects_bad_type(client):
    r = client.post("/agents", json={"name": "X", "type": "scalper", "account_alloc": 1000})
    assert r.status_code == 400


def test_get_missing_agent_404(client):
    assert client.get("/agents/ghost").status_code == 404


def test_record_and_read_cycles(client):
    agent = client.post("/agents", json={"name": "D", "type": "daytrade"}).json()
    aid = agent["id"]
    r = client.post(f"/agents/{aid}/cycles", json={
        "cycle": 1, "decision": "WATCH", "symbol": "AAPL", "score": 18, "max_score": 40,
    })
    assert r.status_code == 200
    cycles = client.get(f"/agents/{aid}/cycles").json()["cycles"]
    assert len(cycles) == 1
    assert cycles[0]["decision"] == "WATCH"


def test_record_cycle_bad_decision_400(client):
    agent = client.post("/agents", json={"name": "D", "type": "swing"}).json()
    r = client.post(f"/agents/{agent['id']}/cycles", json={"cycle": 1, "decision": "MOON"})
    assert r.status_code == 400


def test_cycles_for_missing_agent_404(client):
    assert client.get("/agents/ghost/cycles").status_code == 404


def test_distill_requires_trades(client):
    # No fills → 422 "not enough trades" (does not invoke the LLM)
    aid = client.post("/agents", json={"name": "D", "type": "swing"}).json()["id"]
    client.post(f"/agents/{aid}/cycles", json={"cycle": 1, "decision": "SKIP", "symbol": "AAPL"})
    r = client.post(f"/agents/{aid}/distill")
    assert r.status_code == 422


def test_distill_missing_agent_404(client):
    assert client.post("/agents/ghost/distill").status_code == 404


def test_overview_aggregates(client):
    a = client.post("/agents", json={"name": "A", "type": "swing", "account_alloc": 1000}).json()["id"]
    client.post("/agents", json={"name": "B", "type": "hl_daytrade", "account_alloc": 500})
    # give A a realized win: buy 10@100 then sell 10@110 = +100
    client.post(f"/agents/{a}/cycles", json={"cycle": 1, "decision": "BUY", "symbol": "X", "fill": {"side": "buy", "qty": 10, "price": 100}})
    client.post(f"/agents/{a}/cycles", json={"cycle": 2, "decision": "SELL", "symbol": "X", "fill": {"side": "sell", "qty": 10, "price": 110}})
    ov = client.get("/agents/overview/all").json()
    assert ov["totals"]["count"] == 2
    assert ov["totals"]["alloc"] == 1500.0
    assert ov["totals"]["realized_pnl"] == 100.0
    arow = next(r for r in ov["agents"] if r["id"] == a)
    assert arow["realized_pnl"] == 100.0
    assert arow["return_pct"] == 10.0  # 100/1000
