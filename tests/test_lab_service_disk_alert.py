"""_disk_alert — 6h 스로틀로 디스크 여유공간 확인, warn/critical이면 텔레그램 push."""
from __future__ import annotations

import os

import pytest

from research.lab.service import ResearchService


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.watchdog",
                "jarvis.research_agents.ledger", "research.lab.service"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


def _stub_disk(monkeypatch, free_gb, total_gb=100.0):
    monkeypatch.setattr("api_server.lab_api._disk_free_total_gb", lambda path="research/data": (free_gb, total_gb))


def test_ok_disk_does_not_send(monkeypatch):
    _stub_disk(monkeypatch, free_gb=50.0)
    sent = []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))

    svc = ResearchService()
    svc._disk_alert()

    assert svc.last_disk_check["verdict"] == "ok"
    assert not sent


def test_critical_disk_sends_alert(monkeypatch):
    _stub_disk(monkeypatch, free_gb=1.0)
    sent = []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))

    svc = ResearchService()
    svc._disk_alert()

    assert svc.last_disk_check["verdict"] == "critical"
    assert sent and "디스크" in sent[0]


def test_throttled_within_6h(monkeypatch):
    _stub_disk(monkeypatch, free_gb=1.0)
    sent = []
    monkeypatch.setattr("api_server.lv6_notify.send", lambda text: sent.append(text))

    svc = ResearchService()
    svc._disk_alert()
    svc._disk_alert()

    assert len(sent) == 1
