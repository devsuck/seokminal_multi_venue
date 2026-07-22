"""Tick Quality Controls (P7.2) — 스테일/미래/중복/이상점프. 결정적.

tick_quality(): 이전 틱 + now 기준 quality 등급 산출.
"""
from __future__ import annotations

from jarvis.market_data.models import DUPLICATE, FUTURE, OK, STALE, SUSPECT, hours_between

_EPS = 1e-12


def tick_quality(ts: str, price: float, prev_ts: str | None, prev_price: float | None,
                 now: str | None, stale_seconds: float = 60.0, jump_pct: float = 0.2) -> str:
    """단일 틱 quality. 우선순위: FUTURE > DUPLICATE > SUSPECT > STALE > OK."""
    # 미래 timestamp
    if now is not None:
        age_h = hours_between(ts, now)
        if age_h is not None and age_h < 0:
            return FUTURE
    # 중복(직전과 동일 timestamp)
    if prev_ts is not None and prev_ts == ts:
        return DUPLICATE
    # 이상 점프
    if prev_price is not None and prev_price > _EPS:
        if abs(price / prev_price - 1.0) > jump_pct:
            return SUSPECT
    # 스테일
    if now is not None:
        age_h = hours_between(ts, now)
        if age_h is not None and age_h * 3600.0 > stale_seconds:
            return STALE
    return OK
