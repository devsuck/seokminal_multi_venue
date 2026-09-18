from __future__ import annotations

from fastapi.testclient import TestClient

from api_server.main import app
from api_server.routers import ib_gateway


def _client():
    return TestClient(app, client=("127.0.0.1", 1))


def test_status_reports_connected_when_health_reachable(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"connected": True, "last_auth_ts": "2026-09-14T01:00:00Z",
                     "next_reset_eta": "2026-09-21T01:00:00Z"}

    monkeypatch.setattr(ib_gateway.httpx, "get", lambda url, timeout: FakeResp())

    r = _client().get("/ib/gateway/status")

    assert r.status_code == 200
    body = r.json()
    assert body == {
        "connected": True,
        "last_auth_ts": "2026-09-14T01:00:00Z",
        "next_reset_eta": "2026-09-21T01:00:00Z",
        "needs_manual_action": False,
    }


def test_status_falls_back_to_disconnected_when_unreachable(monkeypatch):
    def _raise(url, timeout):
        raise ConnectionError("VM not deployed yet")

    monkeypatch.setattr(ib_gateway.httpx, "get", _raise)

    r = _client().get("/ib/gateway/status")

    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is False
    assert body["needs_manual_action"] is False
    assert body["error"] == "ib_gateway_unreachable"


def test_status_falls_back_when_health_body_is_not_a_dict(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return ["ok"]

    monkeypatch.setattr(ib_gateway.httpx, "get", lambda url, timeout: FakeResp())

    r = _client().get("/ib/gateway/status")

    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is False
    assert body["error"] == "ib_gateway_unreachable"


def test_status_surfaces_needs_manual_action_flag(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"authenticated": False, "needs_manual_action": True}

    monkeypatch.setattr(ib_gateway.httpx, "get", lambda url, timeout: FakeResp())

    r = _client().get("/ib/gateway/status")

    body = r.json()
    assert body["connected"] is False
    assert body["needs_manual_action"] is True
