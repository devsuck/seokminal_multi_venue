"""edge_providers — 전략별 arm_criteria 호환 GO 판정. 미등록 전략은 항상 False(정직한 기본값)."""
from __future__ import annotations

from jarvis.execution import edge_providers as ep

_GOOD_EDGE = {"status": "ok", "oos_months": 6, "oos_in_envelope": 5}  # ratio 5/6 >= 2/3
_BAD_EDGE = {"status": "ok", "oos_months": 6, "oos_in_envelope": 1}   # ratio 1/6 < kill threshold


def test_unregistered_strategy_always_false():
    assert ep.edge_go("no_such_strategy") is False


def test_buyback_go_when_edge_and_paper_months_sufficient(monkeypatch):
    monkeypatch.setattr("research.paper.buyback_edge.edge_status", lambda: _GOOD_EDGE)
    monkeypatch.setattr("research.paper.buyback_config.FROZEN_AT", "2020-01-01")
    assert ep.edge_go("kr_dart_buyback_drift_v1") is True


def test_buyback_not_go_when_edge_bad(monkeypatch):
    monkeypatch.setattr("research.paper.buyback_edge.edge_status", lambda: _BAD_EDGE)
    monkeypatch.setattr("research.paper.buyback_config.FROZEN_AT", "2020-01-01")
    assert ep.edge_go("kr_dart_buyback_drift_v1") is False


def test_buyback_not_go_when_paper_months_insufficient():
    # FROZEN_AT 실제값 그대로 — 오늘(2026-08) 기준 6개월 구조적 미달([[project_live_execution_bridge_08-25]])
    assert ep.edge_go("kr_dart_buyback_drift_v1") is False


def test_venue_mapping_explicit():
    assert ep.EDGE_PROVIDER_VENUE["kr_dart_buyback_drift_v1"] == "KR"
