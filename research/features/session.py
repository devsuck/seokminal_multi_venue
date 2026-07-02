"""세션(미국 정규장) 유틸. 인트라데이 봉을 거래일별로 그룹 + 개장 후 경과분 계산.

데이터는 useRTH=True로 수집돼 정규장(09:30~16:00 ET)만 포함 가정.
세션 키 = 미국 동부 캘린더 날짜(YYYY-MM-DD)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def session_id(ts_utc: int) -> str:
    """UTC epoch → 미국 동부 거래일 키."""
    return dt.datetime.fromtimestamp(ts_utc, ET).strftime("%Y-%m-%d")


def session_ids(ts: list[int]) -> list[str]:
    return [session_id(t) for t in ts]


def minutes_since_open(ts: list[int], sids: list[str]) -> list[float]:
    """각 봉의 세션 첫 봉(개장) 기준 경과 분. RTH 수집이라 첫 봉 = 09:30 근처."""
    first_ts: dict[str, int] = {}
    for t, s in zip(ts, sids):
        if s not in first_ts or t < first_ts[s]:
            first_ts[s] = t
    return [(t - first_ts[s]) / 60.0 for t, s in zip(ts, sids)]
