"""arm/kill 기준 사전등록 — 데이터 보기 전에 동결된 결정 규칙.

6개월 뒤의 자기합리화 방지: GO/WAIT/KILL이 결정적 코드로 지금 고정된다.
"""
from __future__ import annotations

from jarvis.execution.arm_criteria import CRITERIA, evaluate


def _edge(status="no_oos_yet", oos=0, inside=0):
    return {"status": status, "oos_months": oos, "oos_in_envelope": inside,
            "need_months": 3, "envelope": {"p10": -0.03, "p90": 0.037}}


def test_criteria_frozen_values():
    # 사전등록 값 자체를 고정 — 바꾸려면 이 테스트가 깨져야 함(의도적 마찰)
    assert CRITERIA["min_oos_months"] == 3
    assert CRITERIA["min_paper_months"] == 6
    assert CRITERIA["kill_in_envelope_ratio"] == 0.5
    assert CRITERIA["first_tranche_krw_max"] == 10_000_000


def test_warming_is_wait():
    r = evaluate(_edge(status="warming"), paper_months=12.0)
    assert r["decision"] == "WAIT"
    assert "edge_pending" in r["reasons"]


def test_no_oos_is_wait():
    r = evaluate(_edge(status="no_oos_yet", oos=0), paper_months=0.1)
    assert r["decision"] == "WAIT"


def test_go_requires_oos_ratio_and_paper():
    # OOS 3개월 전부 envelope 내 + 페이퍼 6개월 → GO
    r = evaluate(_edge(status="confirmed", oos=3, inside=3), paper_months=6.0)
    assert r["decision"] == "GO"
    assert r["first_tranche_krw_max"] == 10_000_000


def test_go_blocked_by_insufficient_paper():
    r = evaluate(_edge(status="confirmed", oos=3, inside=3), paper_months=4.0)
    assert r["decision"] == "WAIT"
    assert any("paper" in x for x in r["reasons"])


def test_kill_when_majority_outside_envelope():
    # OOS 4개월 중 1개만 envelope 내(25% < 50%) → KILL
    r = evaluate(_edge(status="drifting", oos=4, inside=1), paper_months=8.0)
    assert r["decision"] == "KILL"


def test_early_drift_is_wait_with_warning():
    # 1개월 이탈만으론 죽이지 않음(성급 금지) — 경고 동반 WAIT
    r = evaluate(_edge(status="drifting", oos=1, inside=0), paper_months=2.0)
    assert r["decision"] == "WAIT"
    assert any("early_drift" in x for x in r["reasons"])


def test_ratio_between_kill_and_go_is_wait():
    # 5개월 중 3개 envelope 내(60%): 죽일 것도(≥50%) 승격할 것도(<2/3) 아님
    r = evaluate(_edge(status="accumulating", oos=5, inside=3), paper_months=12.0)
    assert r["decision"] == "WAIT"
