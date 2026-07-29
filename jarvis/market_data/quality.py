"""Data Quality Layer (P6.4) — 스테일·결측·이상점프·중복ts·미래ts 탐지. 결정적.

MarketDataQualityReport 산출. 읽기전용.
"""
from __future__ import annotations

from jarvis.market_data.models import MarketDataQualityReport, parse_ts

_EPS = 1e-12


def assess_series(symbol: str, bars: list, now: str, stale_hours: float = 48.0,
                  jump_pct: float = 0.5) -> MarketDataQualityReport:
    """bars = [(timestamp, price)]. 시계열 품질 평가."""
    issues: list[dict] = []
    checks: dict = {}
    n = len(bars)

    if n == 0:
        return MarketDataQualityReport(symbol=symbol, n_bars=0, quality_score=0.0,
                                       issues=[{"type": "missing", "detail": "no bars"}],
                                       checks={"missing": True})

    parsed = [(parse_ts(ts), ts, p) for ts, p in bars]
    now_dt = parse_ts(now)

    # 미래 timestamp
    future = [ts for dt, ts, _ in parsed if dt is not None and now_dt is not None and dt > now_dt]
    checks["future_timestamps"] = len(future)
    if future:
        issues.append({"type": "future_timestamp", "detail": future[:5]})

    # 중복 timestamp
    seen: dict = {}
    dups = []
    for dt, ts, _ in parsed:
        seen[ts] = seen.get(ts, 0) + 1
    dups = [ts for ts, c in seen.items() if c > 1]
    checks["duplicate_timestamps"] = len(dups)
    if dups:
        issues.append({"type": "duplicate_timestamp", "detail": sorted(dups)[:5]})

    # 이상 점프(연속 가격 변화율 > jump_pct)
    jumps = []
    ordered = sorted((x for x in parsed if x[0] is not None), key=lambda x: x[0])
    for i in range(1, len(ordered)):
        p0, p1 = ordered[i - 1][2], ordered[i][2]
        if p0 > _EPS and abs(p1 / p0 - 1.0) > jump_pct:
            jumps.append({"from": ordered[i - 1][1], "to": ordered[i][1],
                          "change": round(p1 / p0 - 1.0, 4)})
    checks["abnormal_jumps"] = len(jumps)
    if jumps:
        issues.append({"type": "abnormal_jump", "detail": jumps[:5]})

    # 스테일(최신 bar age)
    last_dt, last_ts, _ = ordered[-1] if ordered else parsed[-1]
    from jarvis.market_data.models import hours_between
    age = hours_between(last_ts, now)
    checks["last_bar_age_hours"] = round(age, 2) if age is not None else None
    if age is not None and age > stale_hours:
        issues.append({"type": "stale", "detail": f"last bar {round(age, 1)}h old (>{stale_hours})"})

    penalty = 0.15 * len(future) + 0.1 * len(dups) + 0.1 * len(jumps) + (0.3 if any(
        i["type"] == "stale" for i in issues) else 0.0)
    score = round(max(0.0, 1.0 - penalty), 4)
    return MarketDataQualityReport(symbol=symbol, n_bars=n, quality_score=score,
                                   issues=issues, checks=checks)


def assess_provider(provider, symbols: list, now: str, stale_hours: float = 48.0) -> dict:
    """CSV류 provider의 심볼별 품질 리포트(bars() 지원 시)."""
    out = {}
    for s in symbols:
        bars = provider.bars(s) if hasattr(provider, "bars") else []
        out[s] = assess_series(s, bars, now, stale_hours).to_dict()
    return out
