"""Opening Range — 세션 초반 N분의 고/저. 돌파 판정용."""
from __future__ import annotations


def opening_range(
    highs: list[float],
    lows: list[float],
    sids: list[str],
    mins_since_open: list[float],
    or_minutes: float = 30.0,
) -> dict:
    """반환: {or_high[], or_low[], in_or_window[]} (봉별).

    or_high/or_low = 그 봉이 속한 세션의 OR 고/저(OR 미형성 세션이면 None).
    in_or_window = 그 봉이 OR 형성 구간(개장~or_minutes 이내)인지 → 진입 금지 구간.
    """
    n = len(highs)
    # 세션별 OR 계산 (개장~or_minutes 봉들의 고/저)
    or_hi: dict[str, float] = {}
    or_lo: dict[str, float] = {}
    for i in range(n):
        if mins_since_open[i] < or_minutes:
            s = sids[i]
            or_hi[s] = max(or_hi.get(s, float("-inf")), highs[i])
            or_lo[s] = min(or_lo.get(s, float("inf")), lows[i])

    out_hi: list[float | None] = []
    out_lo: list[float | None] = []
    in_win: list[bool] = []
    for i in range(n):
        s = sids[i]
        out_hi.append(or_hi.get(s) if s in or_hi else None)
        out_lo.append(or_lo.get(s) if s in or_lo else None)
        in_win.append(mins_since_open[i] < or_minutes)
    return {"or_high": out_hi, "or_low": out_lo, "in_or_window": in_win}
