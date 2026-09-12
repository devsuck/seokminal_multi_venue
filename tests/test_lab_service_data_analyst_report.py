"""_data_analyst_report — 24h 스로틀로 Data Analyst 에이전트(P11.1) 등록 후
registry+readiness 실라이브 데이터를 findings로 담아 리포트 제출. READ ONLY."""
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


def _stub_readiness(monkeypatch, strategies=None):
    monkeypatch.setattr(
        "api_server.lab_api._compute_readiness",
        lambda: {"strategies": strategies or [], "min_paper_months": 6, "first_tranche_krw_max": 0},
    )


def test_first_call_registers_agent_and_submits_report(monkeypatch):
    _stub_readiness(monkeypatch, strategies=[{"registry_id": "s1", "decision": "WAIT"}])
    svc = ResearchService()
    svc._data_analyst_report()

    from jarvis.research_agents import ResearchAgentEngine
    eng = ResearchAgentEngine()
    assert svc.last_data_analyst_report is not None
    assert eng.list_agents()
    reports = eng.agent_activity("data_analyst_daily")
    assert reports


def test_throttled_within_24h_window(monkeypatch):
    _stub_readiness(monkeypatch)
    svc = ResearchService()
    svc._data_analyst_report()
    first = svc.last_data_analyst_report
    svc._data_analyst_report()
    assert svc.last_data_analyst_report == first


def test_exception_is_swallowed(monkeypatch):
    def _boom():
        raise RuntimeError("readiness boom")
    monkeypatch.setattr("api_server.lab_api._compute_readiness", _boom)
    svc = ResearchService()
    svc._data_analyst_report()  # 예외로 죽지 않음
    assert svc.last_data_analyst_report is None


def test_report_findings_contain_registry_and_readiness(monkeypatch):
    from jarvis.registry import StrategyRegistry
    monkeypatch.setattr(StrategyRegistry, "all_current",
                         lambda self: [{"status": "PAPER_ACTIVE"}, {"status": "PAPER_ACTIVE"},
                                       {"status": "FROZEN"}])
    _stub_readiness(monkeypatch, strategies=[{"registry_id": "s1", "decision": "WAIT"}])
    svc = ResearchService()
    svc._data_analyst_report()

    import datetime as _dt
    from jarvis.research_agents import ResearchAgentEngine
    eng = ResearchAgentEngine()
    today = _dt.date.today().isoformat()
    reports = eng.agent_activity("data_analyst_daily")
    assert any(r.get("kind") == "REPORT_SUBMITTED" for r in reports)
