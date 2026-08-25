"""_execution_check — 6h 스로틀로 live_router.route_all() 호출, 결과를 status에 반영.
예외는 다른 _tick 서브틱과 동일하게 조용히 삼킴(research service 전체가 안 죽어야 함)."""
from __future__ import annotations

import os

import pytest

from research.lab.service import ResearchService


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.watchdog"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


def test_first_call_runs_and_records_routed_total(monkeypatch):
    svc = ResearchService()
    monkeypatch.setattr(
        "jarvis.execution.live_router.route_all",
        lambda as_of="": {"as_of": as_of, "routed": [{"instrument": "005930", "result": {}}],
                           "blocked": [], "skipped": []},
    )
    svc._execution_check()
    assert svc.execution_routed_total == 1
    assert svc.last_execution_check is not None
    assert svc.last_execution_result["routed"] == [{"instrument": "005930", "result": {}}]


def test_throttled_within_6h_window(monkeypatch):
    svc = ResearchService()
    calls = []

    def _route_all(as_of=""):
        calls.append(1)
        return {"as_of": as_of, "routed": [], "blocked": [], "skipped": []}
    monkeypatch.setattr("jarvis.execution.live_router.route_all", _route_all)
    svc._execution_check()
    svc._execution_check()
    assert len(calls) == 1


def test_exception_is_swallowed(monkeypatch):
    svc = ResearchService()

    def _boom(as_of=""):
        raise RuntimeError("route_all boom")
    monkeypatch.setattr("jarvis.execution.live_router.route_all", _boom)
    svc._execution_check()  # 예외로 죽지 않음
    assert svc.execution_routed_total == 0


def test_status_exposes_execution_fields():
    svc = ResearchService()
    s = svc.status()
    assert "last_execution_check" in s
    assert "execution_routed_total" in s
    assert "last_execution_result" in s
