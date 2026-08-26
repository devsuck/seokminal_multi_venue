"""arm/kill 기준 v2 — forward-cohort 검증 강화 (FROZEN — 등록 후 동결).

v1(arm_criteria.py)은 edge provider가 낸 oos_months/oos_in_envelope 정수를
그대로 신뢰한다. provider 버그나 since= 파라미터 실수로 동결일 이전 달이나
불리한 달을 조용히 빼먹은 값이 들어와도 v1은 검증할 방법이 없다.

v2는 GO/WAIT/KILL 판정 자체(값)는 그대로 v1에 위임하되, 판정 전에 edge["oos"]
리스트를 독립적으로 재검증한다:
  1) 각 항목에 "month" 태그가 있어야 함(없으면 검증 불가 = WAIT).
  2) 모든 month가 cohort_start(전략 최초 동결일, 사람이 등록 시 고정) 이후여야 함.
  3) cohort_start부터 지금까지 "완결된" 달이 빠짐없이 존재해야 함(월 건너뛰기 =
     불리한 달 cherry-picking 의심 → WAIT). 진짜 데이터 공백(수집 장애 등)도
     이 검사에 걸린다 — 의도된 것: 사람이 직접 확인하기 전엔 승격 안 됨.
검증 실패는 무조건 WAIT — GO는 절대 기본값이 아니다.

기준 변경 = v3 파일 신규 등록(이 파일도 arm_criteria.py처럼 수정 금지).
test_arm_criteria_v2가 값을 고정한다.
"""
from __future__ import annotations

import datetime as _dt

from jarvis.execution.arm_criteria import CRITERIA, evaluate as _v1_evaluate

FROZEN_AT = "2026-08-27"
VERSION = "arm_criteria_v2"


def _expected_forward_months(cohort_start: str, today: _dt.date | None = None) -> list[str]:
    """cohort_start(YYYY-MM-DD) 다음 달부터, 오늘이 속한 달 이전까지 완결된 달들
    ("YYYY-MM"). 진행 중인 이번 달은 아직 forward cohort로 세지 않음 —
    research/paper/*_forward.py의 계산과 정합."""
    start = _dt.date.fromisoformat(cohort_start)
    today = today or _dt.date.today()
    months: list[str] = []
    y, m = start.year, start.month
    while True:
        m += 1
        if m > 12:
            m, y = 1, y + 1
        if (y, m) >= (today.year, today.month):
            break
        months.append(f"{y:04d}-{m:02d}")
    return months


def _verify_forward_cohort(edge: dict, cohort_start: str) -> tuple[bool, str]:
    oos_list = edge.get("oos")
    if not isinstance(oos_list, list) or not oos_list:
        return False, "no_verifiable_oos_cohort_list"

    months = [str(o.get("month")) for o in oos_list if o.get("month")]
    if len(months) != len(oos_list):
        return False, "oos_entry_missing_month_tag"

    cohort_start_ym = cohort_start[:7]
    if any(mo < cohort_start_ym for mo in months):
        return False, "oos_month_before_cohort_start"

    expected = _expected_forward_months(cohort_start)
    if sorted(months) != expected:
        missing = sorted(set(expected) - set(months))
        extra = sorted(set(months) - set(expected))
        return False, f"cohort_calendar_mismatch(missing={missing},extra={extra})"

    return True, "cohort_verified"


def evaluate(edge: dict, paper_months: float, cohort_start: str) -> dict:
    """v1.evaluate()에 forward-cohort 검증을 앞단에 추가한 판정.

    cohort_start(YYYY-MM-DD): 전략을 처음 동결(freeze)한 날짜 — 사람이 등록
    시점에 고정, 이후 불변(각 전략 config 모듈의 FROZEN_AT과 동일해야 함).
    """
    verified, reason = _verify_forward_cohort(edge, cohort_start)
    if not verified:
        return _out("WAIT", [f"forward_cohort_unverified:{reason}"])

    base = _v1_evaluate(edge, paper_months)
    base["reasons"] = [f"cohort_verified({cohort_start})", *base["reasons"]]
    base["version"] = VERSION
    base["frozen_at"] = FROZEN_AT
    return base


def _out(decision: str, reasons: list[str]) -> dict:
    return {"decision": decision, "reasons": reasons, "version": VERSION,
            "frozen_at": FROZEN_AT, "first_tranche_krw_max": CRITERIA["first_tranche_krw_max"]}
