"""파일 기반 kill switch — 프로세스 재시작 없이 즉시 반영(기존 env var 방식은
재시작 필요). set_kill_switch_file()로 토글, RiskConfig.from_env()가 매번 새로 읽음."""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

import live_engine.risk_guard as rg
from api_server.main import app

client = TestClient(app)


def _isolate(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.config.state_path", sp)


def test_file_off_by_default(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.delenv("TRADING_KILL_SWITCH", raising=False)
    assert rg.RiskConfig.from_env().kill_switch is False


def test_set_on_engages_kill_switch(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.delenv("TRADING_KILL_SWITCH", raising=False)
    rg.set_kill_switch_file(True)
    assert rg.RiskConfig.from_env().kill_switch is True


def test_set_off_clears_kill_switch(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.delenv("TRADING_KILL_SWITCH", raising=False)
    rg.set_kill_switch_file(True)
    rg.set_kill_switch_file(False)
    assert rg.RiskConfig.from_env().kill_switch is False


def test_env_var_or_file_either_engages(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("TRADING_KILL_SWITCH", "true")
    # 파일은 꺼져 있어도 env var만으로 engage
    assert rg.RiskConfig.from_env().kill_switch is True


def test_admin_endpoint_toggles(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.delenv("TRADING_KILL_SWITCH", raising=False)
    assert client.get("/admin/kill-switch").json()["kill_switch"] is False
    r = client.post("/admin/kill-switch", json={"on": True})
    assert r.status_code == 200 and r.json()["kill_switch"] is True
    assert client.get("/admin/kill-switch").json()["kill_switch"] is True
    r = client.post("/admin/kill-switch", json={"on": False})
    assert r.json()["kill_switch"] is False
