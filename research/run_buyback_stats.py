"""KR buyback — N=1000 random + 아웃라이어/중앙값 분석 (판정 근거=next_open만).

+1.73% 평균이 아웃라이어 소수에 흔들리는지 = median/trimmed/top-bottom 기여로 확인.
config 동결(next_open/HOLD20). 튜닝 금지.
실행: PYTHONPATH=. python3 research/run_buyback_stats.py
"""
from __future__ import annotations

import bisect
import random as _random
import statistics as _st

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events
from research.validation.baselines import empirical_p_value
from research.paper import buyback_config as CFG
import glob, os

HOLD = CFG.HOLD_DAYS
RT = CFG.COST_BASE_BPS
N_RUNS = 1000
SEED = 42


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _ret(bars, event_date):  # next_open 진입, HOLD 보유, net
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1
    i = j0 + 1
    if j0 < 0 or i >= len(bars["dates"]):
        return None
    entry = bars["open"][i]; xi = min(i + HOLD, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= i:
        return None
    return (bars["close"][xi] / entry - 1) - RT / 10_000.0


def main():
    series = _series()
    bb = load_events("buyback")
    rets = [r for e in bb if e["stock_code"] in series and (r := _ret(series[e["stock_code"]], e["date"])) is not None]
    n = len(rets)
    srt = sorted(rets)
    print("=" * 70 + f"\nKR BUYBACK 통계 안정성 (next_open, n={n}, config 동결)\n" + "=" * 70)

    mean = _st.mean(rets); med = _st.median(rets)
    # 10% trimmed mean
    k = int(n * 0.1)
    trimmed = _st.mean(srt[k:n - k])
    total = sum(rets)
    top5 = srt[-max(1, n // 20):]; bot5 = srt[:max(1, n // 20)]
    win = sum(1 for x in rets if x > 0) / n
    print(f"\n평균 {mean:+.4f} | 중앙값 {med:+.4f} | 10% trimmed {trimmed:+.4f} | 승률 {win:.3f}")
    print(f"상위5% 기여 {sum(top5)/total*100:.1f}% (n={len(top5)}) | 하위5% 기여 {sum(bot5)/total*100:.1f}%")
    # mean이 median보다 훨씬 크면 우편향(소수 대박) → 아웃라이어 의존
    skew_flag = "아웃라이어 의존 의심(평균≫중앙값)" if mean > med * 3 and med > 0 else \
                "중앙값 0 이하(엣지 취약)" if med <= 0 else "중앙값/trimmed도 양수 = 견고"
    print(f"→ {skew_flag}")

    # N=1000 random
    rng = _random.Random(SEED)
    codes = list(series.keys())
    randmeans = []
    for _ in range(N_RUNS):
        s = 0.0
        for _ in range(n):
            b = series[rng.choice(codes)]
            i = rng.randrange(20, max(21, len(b["dates"]) - HOLD - 2))
            e0 = b["open"][i]; xi = min(i + HOLD, len(b["dates"]) - 1)
            s += ((b["close"][xi] / e0 - 1) - RT / 10_000.0) if e0 > 0 else 0.0
        randmeans.append(s / n)
    pv = empirical_p_value(mean, randmeans)
    print(f"\nN=1000 random: pct={pv['percentile']} p={pv['p_value']} (rand_med={pv['random_median']:+.4f})")
    # median 기준 random 비교(아웃라이어 무관 확인)
    rng2 = _random.Random(SEED)
    randmed = []
    for _ in range(N_RUNS):
        rr = []
        for _ in range(n):
            b = series[rng2.choice(codes)]
            i = rng2.randrange(20, max(21, len(b["dates"]) - HOLD - 2))
            e0 = b["open"][i]; xi = min(i + HOLD, len(b["dates"]) - 1)
            rr.append(((b["close"][xi] / e0 - 1) - RT / 10_000.0) if e0 > 0 else 0.0)
        randmed.append(_st.median(rr))
    pvm = empirical_p_value(med, randmed)
    print(f"중앙값 기준 random: pct={pvm['percentile']} p={pvm['p_value']} (rand_med중앙 {pvm['random_median']:+.4f})")
    print("\n판정 근거=next_open만. 위 결과로 파라미터 튜닝 금지.")


if __name__ == "__main__":
    main()
