"""스키마 드리프트 가드 테스트.

이 가드가 2026-07에 있었다면 `actions` vs `action` 사고를 첫날 잡았다.
요구사항 두 가지가 대칭으로 중요하다:
  1. 근거가 쌓였는데 추출 0건이면 반드시 잡을 것
  2. 조용한 에이전트(안 사고 안 파는 중)를 절대 오탐하지 말 것
     — 오탐이 쌓이면 감시는 무시되고, 그게 원래 버그가 6주를 버틴 방식이다.
"""
from __future__ import annotations

import pytest

from api_server import schema_guard
from api_server.agent_perf import compute_performance
from api_server.lv5_learner import compute_lv5_params


@pytest.fixture(autouse=True)
def _clear():
    schema_guard.clear()
    yield
    schema_guard.clear()


def _buy(cycle, symbol="NVDA", price=100.0):
    return {"cycle": cycle, "action": f"buy {symbol}", "best_score": 70,
            "fills": [{"symbol": symbol, "side": "buy", "qty": 1, "price": price}]}


def _close(cycle, symbol="NVDA", price=105.0, pct="+5.0"):
    return {"cycle": cycle, "action": f"close {symbol} (익절 {pct}%)", "best_score": 70,
            "fills": [{"symbol": symbol, "side": "sell", "qty": 1, "price": price}]}


# ── detect_drift 자체 ────────────────────────────────────────────────────────

def test_drift_reported_when_evidence_present_but_nothing_extracted():
    report = schema_guard.detect_drift("p", n_evidence=8, n_extracted=0, hint="h")
    assert report is not None
    assert report["n_evidence"] == 8
    assert schema_guard.recent_drifts()[0]["context"] == "p"


def test_no_drift_when_extraction_succeeded():
    assert schema_guard.detect_drift("p", n_evidence=99, n_extracted=1, hint="h") is None
    assert schema_guard.recent_drifts() == []


def test_no_drift_below_evidence_floor():
    """근거가 적으면 판단 유보 — 성급한 경보가 감시를 죽인다."""
    assert schema_guard.detect_drift("p", n_evidence=4, n_extracted=0, hint="h") is None


# ── 근거 카운터 (파서와 독립적이어야 함) ─────────────────────────────────────

def test_close_actions_counted_under_both_key_spellings():
    """현행 `action`과 과거 버그가 읽던 `actions` 둘 다 세야 파서 독립적이다."""
    cycles = [
        {"action": "close NVDA (익절 +5%)"},
        {"actions": ["청산 000660 (손절 -3%)"]},
        {"action": "buy TSLA"},
        {"action": "none"},
    ]
    assert schema_guard.count_close_actions(cycles) == 2


def test_fill_bearing_counted_under_both_schemas():
    cycles = [
        {"fills": [{"symbol": "A", "side": "buy", "qty": 1, "price": 1}]},
        {"fill": {"side": "buy", "qty": 1, "price": 1}, "fill_symbol": "B"},
        {"fills": []},
        {},
    ]
    assert schema_guard.count_fill_bearing(cycles) == 2


# ── agent_perf 배선 ──────────────────────────────────────────────────────────

def test_agent_perf_flags_unparsed_fill_payloads():
    """`fill` vs `fills` 사고 재현 — 페이로드는 있는데 매칭이 0건."""
    cycles = [{"cycle": i, "fills": [{"sym": "NVDA", "dir": "buy", "n": 1, "px": 100}]}
              for i in range(6)]
    perf = compute_performance(cycles)

    assert perf.trades == []
    drifts = schema_guard.recent_drifts()
    assert drifts and drifts[0]["context"] == "agent_perf.compute_performance"


def test_agent_perf_quiet_when_fills_parse():
    cycles = [_buy(1), _close(2)]
    perf = compute_performance(cycles)

    assert len(perf.trades) == 2
    assert schema_guard.recent_drifts() == []


def test_agent_perf_quiet_for_agent_that_never_traded():
    """조용한 에이전트는 오탐 대상이 아니다 — 체결 페이로드 자체가 없다."""
    cycles = [{"cycle": i, "action": "none"} for i in range(200)]
    perf = compute_performance(cycles)

    assert perf.trades == []
    assert schema_guard.recent_drifts() == []


# ── lv5_learner 배선 ─────────────────────────────────────────────────────────

def test_lv5_alarms_when_closes_recorded_but_no_outcomes():
    """원래 사고 재현 — 청산은 기록됐는데 outcome 0건."""
    cycles = [{"cycle": i, "actions": [f"close NVDA (익절 +5%)"]} for i in range(8)]
    state = compute_lv5_params(cycles, base_threshold=60, base_position_pct=0.1)

    assert state["schema_drift"] is True
    assert "경보" in state["lv5_note"]
    assert "학습중" not in state["lv5_note"]


def test_lv5_cold_start_is_not_an_alarm():
    """신규 에이전트는 청산 기록이 없다 — 평범한 학습중이어야 한다."""
    cycles = [_buy(1), _buy(2)]
    state = compute_lv5_params(cycles, base_threshold=60, base_position_pct=0.1)

    assert state["schema_drift"] is False
    assert "학습중" in state["lv5_note"]
    assert schema_guard.recent_drifts() == []


def test_lv5_quiet_when_outcomes_parse():
    cycles = []
    for i in range(6):
        cycles.append(_buy(i * 2))
        cycles.append(_close(i * 2 + 1))
    state = compute_lv5_params(cycles, base_threshold=60, base_position_pct=0.1)

    assert state["schema_drift"] is False
    assert state["n_trades"] == 6
    assert schema_guard.recent_drifts() == []


def test_lv5_few_closes_stays_cold_start():
    """청산 2건은 근거 부족 — 아직 경보 낼 때가 아니다."""
    cycles = [_buy(1), _close(2), _buy(3), _close(4)]
    state = compute_lv5_params(cycles, base_threshold=60, base_position_pct=0.1)

    assert state["schema_drift"] is False
    assert "학습중" in state["lv5_note"]
