"""KR buyback capacity 체크 — paper 넘기기 전 마지막 게이트.
포지션 사이즈가 종목 ADV(20일평균 거래대금) 대비 몇 %인지로 실현가능한 자본 규모 추정.
룰: 1회 진입 = 해당일 ADV의 5% 이하(기관 관행 상 슬리피지 20~50bps 가정과 정합되는 보수적 상한).
이 상한을 이벤트별로 계산 → 분포 확인 → 동시보유 포지션수(concurrency 진단 median=73)와
곱해서 전체 전략 용량(대략적 AUM 상한) 추정.
실행: PYTHONPATH=. python3 research/run_buyback_capacity_check.py
"""
from __future__ import annotations

import bisect
import statistics as _st
import glob, os

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events

MAX_ADV_PCT = 0.05  # 1회 진입 상한 = ADV의 5%
MEDIAN_CONCURRENT = 73  # run_buyback_concurrency.py 결과


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _adv_at_entry(bars, event_date):
    j = bisect.bisect_right(bars["dates"], event_date)
    if j >= len(bars["dates"]) or bars["open"][j] <= 0:
        return None
    j0 = j - 1
    if j0 < 5:
        return None
    window = bars["tval"][max(0, j0 - 20):j0]
    if not window:
        return None
    adv = _st.mean(window)
    return adv if adv > 0 else None


def main():
    series = _series()
    events = load_events("buyback")
    advs = []
    for e in events:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        adv = _adv_at_entry(b, e["date"])
        if adv is not None:
            advs.append(adv)

    n = len(advs)
    advs.sort()
    caps = sorted(a * MAX_ADV_PCT for a in advs)  # 이벤트별 1회 진입 상한(원)

    print("=" * 74)
    print(f"KR BUYBACK CAPACITY 체크 (1회진입 상한 = ADV × {MAX_ADV_PCT:.0%})")
    print("=" * 74)
    print(f"n={n}\n")

    print("이벤트별 ADV(20일평균 거래대금) 분포:")
    for p in (5, 10, 25, 50, 75, 90, 95):
        idx = min(n - 1, int(n * p / 100))
        print(f"  p{p:<3} = {advs[idx]/1e8:,.1f}억원")

    print(f"\n이벤트별 1회 진입 가능액(ADV의 {MAX_ADV_PCT:.0%}) 분포:")
    for p in (5, 10, 25, 50, 75, 90, 95):
        idx = min(n - 1, int(n * p / 100))
        print(f"  p{p:<3} = {caps[idx]/1e8:,.2f}억원")

    illiquid_100m = sum(1 for c in caps if c < 1e8)
    illiquid_10m = sum(1 for c in caps if c < 1e7)
    print(f"\n1회 진입 가능액 < 1억원인 이벤트: {illiquid_100m}/{n} ({illiquid_100m/n*100:.1f}%)")
    print(f"1회 진입 가능액 < 1천만원인 이벤트: {illiquid_10m}/{n} ({illiquid_10m/n*100:.1f}%)")

    p10_cap = caps[min(n - 1, int(n * 10 / 100))]
    p50_cap = caps[min(n - 1, int(n * 50 / 100))]
    print(f"\n전략 용량(대략적 AUM 상한) 추정 — 동시보유 median={MEDIAN_CONCURRENT}건 가정:")
    print(f"  균등비중(포지션당 p10 캡={p10_cap/1e8:,.2f}억) 적용시: "
          f"약 {p10_cap*MEDIAN_CONCURRENT/1e8:,.0f}억원까지 무리없이 소화 (하위10% 종목까지 커버)")
    print(f"  중앙값 기준(포지션당 p50 캡={p50_cap/1e8:,.2f}억) 적용시: "
          f"약 {p50_cap*MEDIAN_CONCURRENT/1e8:,.0f}억원 — 단, 하위 유동성 종목은 이 사이즈로 못 들어감")
    print("\n(참고) 지금 세션 결론: paper trading 단계에서는 개인/소액 계좌 규모라 위 상한 대비 "
          "여유 매우 큼 — capacity가 실질 제약이 되는 건 운용자산이 수백억 규모로 커진 이후.")


if __name__ == "__main__":
    main()
