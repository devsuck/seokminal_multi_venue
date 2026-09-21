"""KR buyback 보유기간 중 낙폭(MDD) 분포 — 손절 임계치 후보 잡기용 진단. v1 필터 수정 아님.
오염 이벤트(split-시그니처, run_buyback_split_audit.py 확인분) 3건 제외.
실행: PYTHONPATH=. python3 research/run_buyback_drawdown_dist.py
"""
from __future__ import annotations

import bisect
import statistics as _st
import glob, os

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events
from research.paper import buyback_config as CFG

HOLD = CFG.HOLD_DAYS
CONTAMINATED = {("003920", "2024-10-23"), ("363260", "2026-08-10"), ("020180", "2026-07-20")}
CANDIDATES = [-0.05, -0.08, -0.10, -0.12, -0.15, -0.20, -0.25]


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _min_path_return(bars, event_date):
    j = bisect.bisect_right(bars["dates"], event_date)
    if j >= len(bars["dates"]) or bars["open"][j] <= 0:
        return None
    entry = bars["open"][j]
    rets = []
    for k in range(1, HOLD + 1):
        xi = min(j + k, len(bars["dates"]) - 1)
        rets.append(bars["close"][xi] / entry - 1)
        if xi == len(bars["dates"]) - 1:
            break
    if not rets:
        return None
    return min(rets), rets[-1]


def main():
    series = _series()
    events = load_events("buyback")
    mdds, finals = [], []
    for e in events:
        if (e["stock_code"], e["date"]) in CONTAMINATED:
            continue
        b = series.get(e["stock_code"])
        if b is None:
            continue
        r = _min_path_return(b, e["date"])
        if r is None:
            continue
        mdds.append(r[0]); finals.append(r[1])

    n = len(mdds)
    print(f"n={n} (오염 3건 제외)\n")
    mdds_sorted = sorted(mdds)
    print("MDD(보유기간 중 최대낙폭) 분포:")
    for p in (5, 10, 25, 50, 75, 90):
        idx = min(n - 1, int(n * p / 100))
        print(f"  p{p:<3} = {mdds_sorted[idx]*100:+.2f}%")
    print(f"  mean = {_st.mean(mdds)*100:+.2f}%")

    print(f"\n{'threshold':>10}{'trigger_n':>12}{'trigger_%':>11}{'그중 final도 -였던 비율':>26}")
    for th in CANDIDATES:
        idx = [i for i, m in enumerate(mdds) if m <= th]
        n_trig = len(idx)
        would_have_been_neg = sum(1 for i in idx if finals[i] < 0)
        pct_of_triggered_actually_neg = would_have_been_neg / n_trig * 100 if n_trig else 0
        print(f"{th*100:>9.0f}%{n_trig:>12}{n_trig/n*100:>10.1f}%{pct_of_triggered_actually_neg:>25.1f}%")

    print("\n'그중 final도 -였던 비율' 낮으면 = 손절 걸고 나중에 회복했을 이벤트도 같이 끊어버린다는 뜻")
    print("(손절 자르는 대가로 회복 케이스 놓치는 비율 — 임계치 고를 때 이 트레이드오프 같이 볼 것)")


if __name__ == "__main__":
    main()
