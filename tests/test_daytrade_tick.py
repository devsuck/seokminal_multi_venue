"""daytrade-tick smoke: budget/wiring regression (no live network)."""
import pytest
from fastapi.testclient import TestClient

import api_server.router_autopilot as rp
from api_server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    # Avoid network: US scores come back empty → AVOID, no orders.
    monkeypatch.setattr(rp, "_fetch_intraday_bars", lambda s, days=2: [])
    # Alpaca client stub (account + positions)
    class _Acct:  equity = 100000.0
    class _Cli:
        def get_account(self): return _Acct()
        def get_all_positions(self): return []
        def close_position(self, s): pass
        def submit_order(self, r): pass
    monkeypatch.setattr(rp, "_trading_client", lambda *a, **k: _Cli())
    return TestClient(app)


def test_daytrade_tick_us_no_crash(client):
    aid = client.post("/agents", json={"name": "D", "type": "daytrade", "account_alloc": 50000}).json()["id"]
    r = client.post(f"/agents/{aid}/daytrade-tick?cycle=1")
    assert r.status_code == 200
    assert r.json()["decision"] == "SKIP"  # empty scores → no entry
    # cycle recorded
    assert len(client.get(f"/agents/{aid}/cycles").json()["cycles"]) == 1
