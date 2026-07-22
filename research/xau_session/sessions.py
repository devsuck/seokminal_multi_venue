"""XAU Session Confluence — NY 타임존 세션 판정 (순수, tz-aware).

Pine `f_inSession(sess) => not na(time(timeframe.period, sess, "America/New_York"))`을
포팅. 세션 창은 NY 로컬시각으로 정의하고 UTC epoch 봉 타임스탬프를 NY로 변환해 판정.
DST는 zoneinfo가 처리. 자정을 넘는 Asian 세션(19:00→다음날 03:00)은 wrap 케이스로 처리.

세션 창(스펙 §3, Pine 전략 인풋 기본값):
  asian  19:00–03:00 (익일)
  london 02:00–11:30
  ny     08:00–16:00
경계는 [start, end) 반개구간 — 종료시각 봉은 세션 밖(Pine `time()`도 세션 종료봉 na).
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")

# (start, end) — NY 로컬 시:분. end < start 이면 자정을 넘는 세션(wrap).
SESSIONS: dict[str, tuple[time, time]] = {
    "asian": (time(19, 0), time(3, 0)),
    "london": (time(2, 0), time(11, 30)),
    "ny": (time(8, 0), time(16, 0)),
}


def ny_dt(ts_utc: float) -> datetime:
    """UTC epoch(초) → America/New_York aware datetime (DST 반영)."""
    return datetime.fromtimestamp(ts_utc, tz=timezone.utc).astimezone(NY_TZ)


def _in_window(t: time, start: time, end: time) -> bool:
    """t ∈ [start, end)?  end<=start 이면 자정 넘는 창(예: 19:00–03:00)."""
    if start < end:
        return start <= t < end
    # wrap: [start, 24:00) ∪ [00:00, end)
    return t >= start or t < end


def in_session(ts_utc: float, name: str) -> bool:
    """봉 타임스탬프가 세션 창 안인가. 창은 NY 로컬 [start, end) 반개구간."""
    start, end = SESSIONS[name]
    return _in_window(ny_dt(ts_utc).time(), start, end)


def is_session_start(ts_prev_utc: float | None, ts_utc: float, name: str) -> bool:
    """직전 봉은 세션 밖이고 현재 봉이 세션 안 → 이 봉이 세션 시작봉.
    ts_prev_utc=None(첫 봉)이면 현재 봉의 세션 소속 여부로 판정."""
    now_in = in_session(ts_utc, name)
    if not now_in:
        return False
    if ts_prev_utc is None:
        return True
    return not in_session(ts_prev_utc, name)


def is_session_end(ts_prev_utc: float | None, ts_utc: float, name: str) -> bool:
    """직전 봉은 세션 안이고 현재 봉이 세션 밖 → 세션 종료가 직전 봉과 현재 봉 사이에서
    발생. '아시안 종료 시점 레인지 고정'을 현재 봉(세션 이탈 첫 봉)에서 트리거하는 용도."""
    if ts_prev_utc is None:
        return False
    return in_session(ts_prev_utc, name) and not in_session(ts_utc, name)
