"""세션 리셋 VWAP. 각 거래일마다 누적 리셋."""
from __future__ import annotations


def session_vwap(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    sids: list[str],
) -> list[float | None]:
    """봉별 VWAP(세션 누적). typical=(H+L+C)/3, VWAP=Σ(tp·vol)/Σvol.
    거래량 0 누적 구간은 None."""
    n = len(closes)
    out: list[float | None] = [None] * n
    cur_sid: str | None = None
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(n):
        if sids[i] != cur_sid:
            cur_sid = sids[i]
            cum_pv = 0.0
            cum_v = 0.0
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        cum_pv += tp * volumes[i]
        cum_v += volumes[i]
        out[i] = (cum_pv / cum_v) if cum_v > 0 else None
    return out
