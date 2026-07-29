"""daytrade-tick smoke: budget/wiring regression (no live network)."""
import pytest
from fastapi.testclient import TestClient

from api_server.routers import alpaca_shared as shared
from api_server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    # Avoid network: US scores come back empty → AVOID, no orders.
    monkeypatch.setattr(shared, "_fetch_intraday_bars", lambda s, days=2: [])
    # Alpaca client stub (account + positions)
    class _Acct:  equity = 100000.0
    class _Cli:
        def get_account(self): return _Acct()
        def get_all_positions(self): return []
        def close_position(self, s): pass
        def submit_order(self, r): pass
    monkeypatch.setattr(shared, "_trading_client", lambda *a, **k: _Cli())
    return TestClient(app)


def test_daytrade_tick_us_no_crash(client):
    aid = client.post("/agents", json={"name": "D", "type": "daytrade", "account_alloc": 50000}).json()["id"]
    r = client.post(f"/agents/{aid}/daytrade-tick?cycle=1")
    assert r.status_code == 200
    assert r.json()["decision"] == "SKIP"  # empty scores → no entry
    # cycle recorded
    assert len(client.get(f"/agents/{aid}/cycles").json()["cycles"]) == 1


def test_swing_kr_routes_to_kr_not_us(client, monkeypatch):
    """스윙(장투) 봇 + market=KR → KR 실행(KIS), US(Alpaca) 아님. 통화 오라우팅 회귀."""
    monkeypatch.setattr(shared, "_fetch_kr_intraday_bars", lambda s: [])

    class _KIS:
        def __init__(self, *a, **k): pass
        def get_balance(self): return {"net_asset": 1000000.0}
        def get_holdings(self): return []
        def place_order(self, *a, **k): return {"order_id": "1"}
    monkeypatch.setattr("backends.kis.order_client.KISOrderClient", _KIS)

    aid = client.post("/agents", json={
        "name": "KRswing", "type": "swing", "market": "KR", "account_alloc": 1000000,
    }).json()["id"]
    r = client.post(f"/agents/{aid}/daytrade-tick?cycle=1")
    assert r.status_code == 200
    assert r.json()["venue"] == "KR"  # not US → no Alpaca/USD order
