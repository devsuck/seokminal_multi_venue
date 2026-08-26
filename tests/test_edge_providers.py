"""edge_providers — 전략별 arm_criteria v2 호환 GO 판정(forward-cohort 검증 포함).
미등록 전략은 항상 False(정직한 기본값)."""
from __future__ import annotations

import datetime as _dt

from jarvis.execution import edge_providers as ep
from jarvis.execution.arm_criteria_v2 import _expected_forward_months


def _shift_month(y: int, m: int, delta: int) -> tuple[int, int]:
    idx = (y * 12 + (m - 1)) + delta
    return idx // 12, idx % 12 + 1


def _cohort_start_for_months(n: int) -> str:
    """오늘 기준 정확히 n개의 완결된 forward 달이 나오는 cohort_start(YYYY-MM-DD)."""
    today = _dt.date.today()
    y, m = _shift_month(today.year, today.month, -(n + 1))
    return f"{y:04d}-{m:02d}-01"


def _edge_with_oos(cohort_start: str, n_total: int, n_in: int) -> dict:
    months = _expected_forward_months(cohort_start)
    assert len(months) == n_total
    oos = [{"month": m, "in_envelope": i < n_in} for i, m in enumerate(months)]
    return {"status": "ok", "oos_months": n_total, "oos_in_envelope": n_in, "oos": oos}


# ratio 5/6 >= 2/3(GO), 1/6 < kill threshold(KILL) — cohort_start는 각 테스트가 계산.
_COHORT_START = _cohort_start_for_months(6)
_GOOD_EDGE = _edge_with_oos(_COHORT_START, 6, 5)
_BAD_EDGE = _edge_with_oos(_COHORT_START, 6, 1)


def test_unregistered_strategy_always_false():
    assert ep.edge_go("no_such_strategy") is False


def test_buyback_go_when_edge_and_paper_months_sufficient(monkeypatch):
    monkeypatch.setattr("research.paper.buyback_edge.edge_status", lambda: _GOOD_EDGE)
    monkeypatch.setattr("research.paper.buyback_config.FROZEN_AT", _COHORT_START)
    assert ep.edge_go("kr_dart_buyback_drift_v1") is True


def test_buyback_not_go_when_edge_bad(monkeypatch):
    monkeypatch.setattr("research.paper.buyback_edge.edge_status", lambda: _BAD_EDGE)
    monkeypatch.setattr("research.paper.buyback_config.FROZEN_AT", _COHORT_START)
    assert ep.edge_go("kr_dart_buyback_drift_v1") is False


def test_buyback_not_go_when_paper_months_insufficient():
    # FROZEN_AT 실제값 그대로 — 오늘(2026-08) 기준 6개월 구조적 미달([[project_live_execution_bridge_08-25]])
    assert ep.edge_go("kr_dart_buyback_drift_v1") is False


def test_buyback_not_go_when_forward_cohort_unverifiable(monkeypatch):
    # oos 리스트에 month 태그가 없으면(v1 시절 포맷) v2가 검증 불가 → WAIT → GO 아님.
    stale_shape_edge = {"status": "ok", "oos_months": 6, "oos_in_envelope": 5}
    monkeypatch.setattr("research.paper.buyback_edge.edge_status", lambda: stale_shape_edge)
    monkeypatch.setattr("research.paper.buyback_config.FROZEN_AT", _COHORT_START)
    assert ep.edge_go("kr_dart_buyback_drift_v1") is False


def test_venue_mapping_explicit():
    assert ep.EDGE_PROVIDER_VENUE["kr_dart_buyback_drift_v1"] == "KR"


def test_tsmom_go_when_edge_and_paper_months_sufficient(monkeypatch):
    monkeypatch.setattr("research.paper.tsmom_edge.edge_status", lambda: _GOOD_EDGE)
    monkeypatch.setattr("research.paper.tsmom_config.FROZEN_AT", _COHORT_START)
    assert ep.edge_go("futures_tsmom_32mkt") is True


def test_tsmom_not_go_when_edge_bad(monkeypatch):
    monkeypatch.setattr("research.paper.tsmom_edge.edge_status", lambda: _BAD_EDGE)
    monkeypatch.setattr("research.paper.tsmom_config.FROZEN_AT", _COHORT_START)
    assert ep.edge_go("futures_tsmom_32mkt") is False


def test_tsmom_not_go_when_paper_months_insufficient():
    assert ep.edge_go("futures_tsmom_32mkt") is False


def test_tsmom_venue_unregistered():
    # futures/32개 시장 — 단일 venue 없음, live_router가 unsupported_venue로 거부.
    assert "futures_tsmom_32mkt" not in ep.EDGE_PROVIDER_VENUE


def test_tom_go_when_edge_and_paper_months_sufficient(monkeypatch):
    monkeypatch.setattr("research.paper.tom_edge.edge_status", lambda: _GOOD_EDGE)
    monkeypatch.setattr("research.paper.tom_config.FROZEN_AT", _COHORT_START)
    assert ep.edge_go("kr_turn_of_month_v1_PORTFOLIO") is True


def test_tom_not_go_when_edge_bad(monkeypatch):
    monkeypatch.setattr("research.paper.tom_edge.edge_status", lambda: _BAD_EDGE)
    monkeypatch.setattr("research.paper.tom_config.FROZEN_AT", _COHORT_START)
    assert ep.edge_go("kr_turn_of_month_v1_PORTFOLIO") is False


def test_tom_not_go_when_paper_months_insufficient():
    assert ep.edge_go("kr_turn_of_month_v1_PORTFOLIO") is False


def test_tom_venue_mapping_explicit():
    assert ep.EDGE_PROVIDER_VENUE["kr_turn_of_month_v1_PORTFOLIO"] == "KR"


def test_cohort_start_registered_for_all_venued_strategies():
    for strategy_id in ep.EDGE_PROVIDER_VENUE:
        assert strategy_id in ep.EDGE_PROVIDER_COHORT_START, strategy_id
