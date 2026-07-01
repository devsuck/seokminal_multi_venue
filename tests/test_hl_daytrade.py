"""HL day-trade profile + leverage request validation (no network)."""
from fastapi.testclient import TestClient

from api_server.main import app
from api_server.agent_store import AGENT_PROFILES

client = TestClient(app)


def test_hl_daytrade_profile_registered():
    p = AGENT_PROFILES["hl_daytrade"]
    assert p["venue"] == "HL"
    assert p["leverage"] >= 1
    assert p["paper"] is True
    assert 0 < p["position_pct"] <= 1


def test_leverage_over_cap_rejected_by_schema():
    # Field(ge=1, le=50) → 422 before the handler touches the network
    r = client.post("/hl/leverage", json={"coin": "BTC", "leverage": 100})
    assert r.status_code == 422


def test_leverage_zero_rejected():
    r = client.post("/hl/leverage", json={"coin": "BTC", "leverage": 0})
    assert r.status_code == 422
