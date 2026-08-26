"""POST/GET /steward/heartbeat 라우터 스모크."""
from fastapi.testclient import TestClient

from api_server.main import app


def test_heartbeat_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.config.STATE_DIR", str(tmp_path))
    client = TestClient(app)

    before = client.get("/steward/heartbeat").json()
    assert before["last_heartbeat"] is None
    assert before["expired"] is True
    assert before["deadman_days"] == 7

    posted = client.post("/steward/heartbeat")
    assert posted.status_code == 200
    assert posted.json()["ok"] is True

    after = client.get("/steward/heartbeat").json()
    assert after["last_heartbeat"] is not None
    assert after["expired"] is False
