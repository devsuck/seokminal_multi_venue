"""arm_criteria v2 — forward-cohort 재검증 레이어(FROZEN — 등록 후 동결).

v1(test_arm_criteria.py)의 GO/WAIT/KILL 값 자체는 그대로 위임되므로 여기서는
재검증하지 않는다. 여기서 고정하는 건 v2가 새로 추가한 것: oos 리스트 없음/월
태그 없음/cohort_start 이전 월/달력 공백-초과 → 전부 WAIT, 그리고 검증 통과 시
v1로 정확히 위임되는지.
"""
from __future__ import annotations

import datetime as _dt

from jarvis.execution.arm_criteria import CRITERIA
from jarvis.execution.arm_criteria_v2 import FROZEN_AT, VERSION, _expected_forward_months, evaluate


def _shift_month(y: int, m: int, delta: int) -> tuple[int, int]:
    idx = (y * 12 + (m - 1)) + delta
    return idx // 12, idx % 12 + 1


def _cohort_start_for_months(n: int) -> str:
    today = _dt.date.today()
    y, m = _shift_month(today.year, today.month, -(n + 1))
    return f"{y:04d}-{m:02d}-01"


def _edge(months: list[str], inside: int, status="confirmed") -> dict:
    oos = [{"month": m, "in_envelope": i < inside} for i, m in enumerate(months)]
    return {"status": status, "oos_months": len(oos), "oos_in_envelope": inside,
            "need_months": 3, "envelope": {"p10": -0.03, "p90": 0.037}, "oos": oos}


def test_version_and_frozen_at_constants():
    assert VERSION == "arm_criteria_v2"
    assert FROZEN_AT == "2026-08-27"


def test_criteria_reused_from_v1_not_duplicated():
    # v2는 CRITERIA를 값으로 복제하지 않고 v1 걸 그대로 import — 동일 객체.
    assert CRITERIA["first_tranche_krw_max"] == 10_000_000


def test_missing_oos_key_is_wait():
    cohort_start = _cohort_start_for_months(3)
    edge = {"status": "confirmed", "oos_months": 3, "oos_in_envelope": 3}
    r = evaluate(edge, paper_months=6.0, cohort_start=cohort_start)
    assert r["decision"] == "WAIT"
    assert any("no_verifiable_oos_cohort_list" in x for x in r["reasons"])


def test_empty_oos_list_is_wait():
    cohort_start = _cohort_start_for_months(3)
    edge = _edge([], inside=0)
    r = evaluate(edge, paper_months=6.0, cohort_start=cohort_start)
    assert r["decision"] == "WAIT"
    assert any("no_verifiable_oos_cohort_list" in x for x in r["reasons"])


def test_oos_entry_missing_month_tag_is_wait():
    cohort_start = _cohort_start_for_months(3)
    months = _expected_forward_months(cohort_start)
    edge = _edge(months, inside=3)
    edge["oos"][0].pop("month")
    r = evaluate(edge, paper_months=6.0, cohort_start=cohort_start)
    assert r["decision"] == "WAIT"
    assert any("oos_entry_missing_month_tag" in x for x in r["reasons"])


def test_month_before_cohort_start_is_wait():
    cohort_start = _cohort_start_for_months(3)
    months = _expected_forward_months(cohort_start)
    # cohort_start보다 1년 앞선 달을 섞어넣음 — 동결일 이전 데이터 오염 시나리오.
    y, m = _dt.date.fromisoformat(cohort_start).year - 1, _dt.date.fromisoformat(cohort_start).month
    edge = _edge([f"{y:04d}-{m:02d}", *months[1:]], inside=len(months))
    r = evaluate(edge, paper_months=6.0, cohort_start=cohort_start)
    assert r["decision"] == "WAIT"
    assert any("oos_month_before_cohort_start" in x for x in r["reasons"])


def test_missing_month_in_calendar_is_wait():
    cohort_start = _cohort_start_for_months(4)
    months = _expected_forward_months(cohort_start)
    edge = _edge(months[:-1], inside=len(months) - 1)  # 마지막 달 누락(불리한 달 cherry-pick 의심)
    r = evaluate(edge, paper_months=6.0, cohort_start=cohort_start)
    assert r["decision"] == "WAIT"
    assert any("cohort_calendar_mismatch" in x for x in r["reasons"])


def test_extra_month_in_calendar_is_wait():
    cohort_start = _cohort_start_for_months(3)
    months = _expected_forward_months(cohort_start)
    today_ym = _dt.date.today().strftime("%Y-%m")
    edge = _edge([*months, today_ym], inside=len(months) + 1)  # 아직 안 끝난 이번 달을 끼워넣음
    r = evaluate(edge, paper_months=6.0, cohort_start=cohort_start)
    assert r["decision"] == "WAIT"
    assert any("cohort_calendar_mismatch" in x for x in r["reasons"])


def test_valid_cohort_delegates_go_to_v1():
    cohort_start = _cohort_start_for_months(3)
    months = _expected_forward_months(cohort_start)
    edge = _edge(months, inside=3)  # 3/3 envelope 내 + need_months=3 충족
    r = evaluate(edge, paper_months=6.0, cohort_start=cohort_start)
    assert r["decision"] == "GO"
    assert r["version"] == VERSION
    assert r["frozen_at"] == FROZEN_AT
    assert any(f"cohort_verified({cohort_start})" in x for x in r["reasons"])
    assert r["first_tranche_krw_max"] == CRITERIA["first_tranche_krw_max"]


def test_valid_cohort_delegates_kill_to_v1():
    cohort_start = _cohort_start_for_months(4)
    months = _expected_forward_months(cohort_start)
    edge = _edge(months, inside=1, status="drifting")  # 1/4 = 25% < kill 50%
    r = evaluate(edge, paper_months=8.0, cohort_start=cohort_start)
    assert r["decision"] == "KILL"


def test_valid_cohort_still_blocked_by_insufficient_paper_months():
    cohort_start = _cohort_start_for_months(3)
    months = _expected_forward_months(cohort_start)
    edge = _edge(months, inside=3)
    r = evaluate(edge, paper_months=1.0, cohort_start=cohort_start)
    assert r["decision"] == "WAIT"
    assert any("paper" in x for x in r["reasons"])
