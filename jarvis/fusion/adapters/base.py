"""어댑터 공통 — 결정시각 파싱 + no-lookahead 가드.

원칙: 어댑터는 전략 로직을 재구현/수정하지 않는다. 전략 자신의 신호함수·
지속상태를 결정시각(as_of) 이하 정보만으로 StrategySignal로 번역한다.
"""
from __future__ import annotations

import datetime as _dt


def as_date(ts: str) -> str | None:
    """as_of(‘YYYY-MM-DD’ 또는 ISO) → ‘YYYY-MM-DD’. 파싱 실패 시 None."""
    if not ts:
        return None
    s = str(ts)[:10]
    try:
        _dt.date.fromisoformat(s)
        return s
    except ValueError:
        return None


def last_business_day(year: int, month: int) -> str:
    """해당 월 마지막 평일(월~금). 거래소 휴장일 미반영(근사) — 블로커로 문서화."""
    d = _dt.date(year, 12, 31) if month == 12 else _dt.date(year, month + 1, 1) - _dt.timedelta(days=1)
    while d.weekday() >= 5:  # 5=토,6=일
        d -= _dt.timedelta(days=1)
    return d.isoformat()


def add_business_days(date_iso: str, n: int) -> str:
    """평일 기준 n영업일 뒤 날짜(근사, 휴장일 미반영)."""
    d = _dt.date.fromisoformat(date_iso)
    step = 0
    while step < n:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5:
            step += 1
    return d.isoformat()
