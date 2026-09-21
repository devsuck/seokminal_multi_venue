"""KR buyback 이벤트 동시노출(concurrency)/섹터 집중도 진단 — 사이징 설계 전 선행 체크.
v1 동결, 필터 수정 아님. 1978건이 통계적으로 독립처럼 검증됐어도 실제 동시보유 종목수가
적으면(같은 날/주 몰림) 분산 효과가 과대평가된 것 — 사이징 결정 전에 확인.
실행: PYTHONPATH=. python3 research/run_buyback_concurrency.py
"""
from __future__ import annotations

import bisect
import collections
import glob, os
import statistics as _st

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events
from research.paper import buyback_config as CFG

HOLD = CFG.HOLD_DAYS


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _window(bars, event_date):
    """진입일(entry_date), 청산일(exit_date), sect 반환. None이면 매칭 실패."""
    j = bisect.bisect_right(bars["dates"], event_date)
    if j >= len(bars["dates"]) or bars["open"][j] <= 0:
        return None
    xi = min(j + HOLD, len(bars["dates"]) - 1)
    if xi <= j:
        return None
    return bars["dates"][j], bars["dates"][xi], (bars["sect"][j] or bars.get("market", ""))


def main():
    series = _series()
    events = load_events("buyback")
    windows = []  # (entry_date, exit_date, sect, stock_code)
    for e in events:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        w = _window(b, e["date"])
        if w is None:
            continue
        entry, exit_, sect = w
        windows.append((entry, exit_, sect, e["stock_code"]))

    print(f"n={len(windows)}\n")

    # 1) 날짜별 동시 오픈 포지션 수 — HOLD윈도 겹치는 이벤트 카운트
    all_dates = sorted({d for w in windows for d in (w[0], w[1])})
    concurrent = []
    for d in all_dates:
        c = sum(1 for entry, exit_, _, _ in windows if entry <= d <= exit_)
        concurrent.append(c)
    concurrent.sort()
    n = len(concurrent)
    print("날짜별 동시보유 포지션 수 분포 (거래대상일 기준):")
    for p in (50, 75, 90, 95, 99, 100):
        idx = min(n - 1, int(n * p / 100))
        print(f"  p{p:<3} = {concurrent[idx]}")
    print(f"  mean = {_st.mean(concurrent):.1f}")

    # 2) 같은 날 진입(entry) 이벤트 수 — 발표일 몰림 체크
    entry_counts = collections.Counter(w[0] for w in windows)
    same_day = sorted(entry_counts.values(), reverse=True)
    print(f"\n같은날 진입 최대: {same_day[0]}건, 상위5: {same_day[:5]}")
    multi_entry_days = sum(1 for c in entry_counts.values() if c > 1)
    print(f"진입일 {len(entry_counts)}개 중 2건 이상 겹친 날: {multi_entry_days}개 "
          f"({multi_entry_days/len(entry_counts)*100:.1f}%)")

    # 3) 동시보유 시점의 섹터(sect) 집중도 — 피크 동시보유일 하나 골라서 구성 확인
    peak_date = all_dates[max(range(len(all_dates)), key=lambda i: sum(
        1 for entry, exit_, _, _ in windows if entry <= all_dates[i] <= exit_))]
    peak_members = [(code, sect) for entry, exit_, sect, code in windows if entry <= peak_date <= exit_]
    sect_counter = collections.Counter(s for _, s in peak_members)
    print(f"\n피크 동시보유일 {peak_date} — 총 {len(peak_members)}건, 섹터(sect) 분포:")
    for sect, c in sect_counter.most_common(10):
        print(f"  {sect or '(미분류)'}: {c}")


if __name__ == "__main__":
    main()
