"""KR buyback v1 룰(next_open, HOLD20)로 마이너스 난 이벤트 나열 — 진단용, 필터 수정 아님.
실행: PYTHONPATH=. python3 research/run_buyback_losers.py
"""
from __future__ import annotations

import bisect
import glob, os

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events, pull_buyback_details
from research.paper import buyback_config as CFG

HOLD = CFG.HOLD_DAYS
RT = CFG.COST_BASE_BPS


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _fwd(bars, event_date):
    j = bisect.bisect_right(bars["dates"], event_date)
    if j >= len(bars["dates"]) or bars["open"][j] <= 0:
        return None
    entry = bars["open"][j]
    xi = min(j + HOLD, len(bars["dates"]) - 1)
    if xi <= j:
        return None
    return (bars["close"][xi] / entry - 1) - RT / 10_000.0


def main():
    events = load_events("buyback")
    corps = sorted({e["corp_code"] for e in events if e.get("corp_code")})
    details = pull_buyback_details(corps, "20240101", "20260921")
    dmap = {(d["corp_code"], d["rcept_dt"]): d for d in details}

    series = _series()
    rows = []
    for e in events:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        r = _fwd(b, e["date"])
        if r is None:
            continue
        d = dmap.get((e["corp_code"], e["date"].replace("-", "")))
        purpose = d.get("purpose", "") if d else ""
        rows.append((r, e["stock_code"], b.get("name", ""), e["date"], purpose))

    rows.sort()
    neg = [r for r in rows if r[0] < 0]
    print(f"전체 {len(rows)}건 중 마이너스 {len(neg)}건 ({len(neg)/len(rows)*100:.1f}%)\n")
    print(f"{'ret':>8}  {'code':<8}{'name':<14}{'date':<12}{'purpose'}")
    for r, code, name, date, purpose in rows[:30]:
        print(f"{r*100:+7.2f}%  {code:<8}{name:<14}{date:<12}{purpose[:30]}")

    print(f"\n... 최악 30건 위 표시. 마이너스 전체 {len(neg)}건 중 소각 비율: "
          f"{sum(1 for r in neg if '소각' in r[4])}/{len(neg)}")


if __name__ == "__main__":
    main()
