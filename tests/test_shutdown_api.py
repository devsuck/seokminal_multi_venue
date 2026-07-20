"""/alpaca/shutdown/* — autopilot tmux 세션 없을 때 폴링이 무한 대기하던 버그 회귀 테스트."""
import time

from fastapi.testclient import TestClient

from api_server import router_autopilot
from api_server.main import app

client = TestClient(app)


def test_status_reports_done_when_no_tmux_session(monkeypatch):
    monkeypatch.setattr(router_autopilot, "_tmux_session_exists", lambda: False)

    r = client.get("/alpaca/shutdown/status")

    assert r.status_code == 200
    body = r.json()
    assert body["done"] is True


def test_status_waits_for_handoff_complete_when_session_exists(monkeypatch):
    monkeypatch.setattr(router_autopilot, "_tmux_session_exists", lambda: True)
    monkeypatch.setattr(router_autopilot, "_tmux_capture", lambda n=200: ["working...", "still going"])

    r = client.get("/alpaca/shutdown/status")

    assert r.json()["done"] is False


def test_status_done_once_handoff_complete_marker_appears(monkeypatch):
    monkeypatch.setattr(router_autopilot, "_tmux_session_exists", lambda: True)
    monkeypatch.setattr(router_autopilot, "_tmux_capture", lambda n=200: ["work done", "HANDOFF_COMPLETE"])

    r = client.get("/alpaca/shutdown/status")

    assert r.json()["done"] is True


def test_initiate_skips_tmux_commands_when_no_session(monkeypatch, tmp_path):
    monkeypatch.setattr(router_autopilot, "_tmux_session_exists", lambda: False)
    monkeypatch.setattr(router_autopilot, "KILL_FILE", str(tmp_path / "KILL"))

    calls = []
    monkeypatch.setattr(
        router_autopilot.subprocess, "run",
        lambda *a, **k: calls.append(a) or type("R", (), {"returncode": 0})(),
    )

    r = client.post("/alpaca/shutdown/initiate")

    assert r.status_code == 200
    assert calls == []  # no tmux send-keys attempted against a session that doesn't exist
    assert (tmp_path / "KILL").read_text() == "shutdown\n"


def test_initiate_sends_handoff_when_session_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(router_autopilot, "_tmux_session_exists", lambda: True)
    monkeypatch.setattr(router_autopilot, "KILL_FILE", str(tmp_path / "KILL"))
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    calls = []
    monkeypatch.setattr(
        router_autopilot.subprocess, "run",
        lambda *a, **k: calls.append(a) or type("R", (), {"returncode": 0})(),
    )

    r = client.post("/alpaca/shutdown/initiate")

    assert r.status_code == 200
    assert len(calls) == 3  # 2x Ctrl-C + handoff command
