"""RVOL(상대거래량) — 같은 시간대(개장 후 경과분 버킷)의 과거 N세션 평균 대비.

봉별 rvol = vol[i] / mean(같은 슬롯의 직전 N세션 vol). 과거 표본 부족 시 None."""
from __future__ import annotations


def rvol(
    volumes: list[float],
    sids: list[str],
    mins_since_open: list[float],
    lookback_sessions: int = 20,
    min_sessions: int = 5,
) -> list[float | None]:
    n = len(volumes)
    out: list[float | None] = [None] * n
    # 슬롯(경과분 반올림) → 지금까지 본 과거 볼륨 이력
    hist: dict[float, list[float]] = {}
    for i in range(n):
        slot = round(mins_since_open[i])
        past = hist.get(slot, [])
        if len(past) >= min_sessions:
            window = past[-lookback_sessions:]
            avg = sum(window) / len(window)
            if avg > 0:
                out[i] = volumes[i] / avg
        # 이번 봉 볼륨을 이력에 추가(자기 자신은 미래참조라 판정 후 추가)
        hist.setdefault(slot, []).append(volumes[i])
    return out
