"""kr_turn_of_month 정직 재검 — 포트폴리오 레벨(종목간 상관 뻥튀기 제거).

풀링(n=49057)은 월말 시장 공통변동으로 상관↑ → p 과장. 진짜 = 월별 EW 포트 수익 1개씩(n≈월수).
각 월: 유동종목 월말진입 4일보유 EW 평균. random = 같은 구조 랜덤 진입일. 실행: PYTHONPATH=. python3 research/run_tom_portfolio.py
"""
from __future__ import annotations

import bisect
import glob
import os
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.krx_api import build_series, market_dir
from research.validation.baselines import empirical_p_value

HOLD = 4
COST_RT = 40 / 1e4
N_RUNS = 500
SEED = 42


def main():
    print("kr_turn_of_month 포트폴리오-레벨 재검 (상관 뻥튀기 제거)")
    s = build_series("KOSDAQ", min_bars=300)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=300))
    liquid = [b for b in s.values() if len(b["close"]) >= 300
              and _st.mean(b["tval"][-20:]) >= 1e9 and b["marcap"][-1] >= 5e10]
    all_dates = sorted(set().union(*[set(b["dates"]) for b in liquid]))
    # 월 마지막 거래일
    tom_days, seen = [], {}
    for i, d in enumerate(all_dates[:-1]):
        if d[:7] != all_dates[i + 1][:7]:
            tom_days.append(d)

    def at(b, d):
        j = bisect.bisect_right(b["dates"], d) - 1
        return j if j >= 0 else None

    def month_ret(entry_day_of, rng_pick=None):
        """entry_day_of: 각 종목 진입 인덱스 함수. 월별 EW 수익 리스트."""
        out = []
        for d in tom_days:
            rs = []
            for b in liquid:
                k = at(b, d)
                if k is None or k < 10 or k + HOLD >= len(b["close"]):
                    continue
                ki = rng_pick(b, k) if rng_pick else k
                if ki + HOLD >= len(b["close"]) or b["close"][ki] <= 0:
                    continue
                rs.append(b["close"][ki + HOLD] / b["close"][ki] - 1 - COST_RT)
            if rs:
                out.append(_st.mean(rs))
        return out

    strat = month_ret(None)
    smean = _st.mean(strat)
    rng = _random.Random(SEED)
    rand_means = []
    for _ in range(N_RUNS):
        def pick(b, k):
            lo = max(10, 0); hi = len(b["close"]) - HOLD - 1
            return rng.randint(lo, hi) if hi > lo else k
        rand_means.append(_st.mean(month_ret(None, pick)))
    ev = empirical_p_value(smean, rand_means)
    mid = len(strat) // 2
    wf1, wf2 = _st.mean(strat[:mid]), _st.mean(strat[mid:])
    print(f"\n포트폴리오 월수 n={len(strat)} | 평균 월말수익 {smean:+.4%}")
    print(f"vs random(포트레벨): pct={ev['percentile']} p={ev['p_value']} (med={ev['random_median']:+.4%})")
    print(f"walk-forward: 전반 {wf1:+.4%} / 후반 {wf2:+.4%}")

    pct = ev["percentile"] or 0.0
    passed = smean > 0 and pct >= 95 and (ev["p_value"] or 1) < 0.05 and wf1 > 0 and wf2 > 0
    verdict = ("EDGE 후보(포트레벨) — 상관보정 후에도 생존" if passed else
               "WEAK — 포트레벨선 유의 약화" if smean > 0 and pct >= 80 else
               "REJECT — 상관보정하니 엣지 소멸(풀링이 뻥튀기였음)")
    print(f"\nVERDICT: {verdict}")
    log_experiment({"hypothesis_id": "kr_turn_of_month_v1_PORTFOLIO", "status": "watchlist" if passed else "rejected" if pct < 80 else "weak",
                    "n_months": len(strat), "net": round(smean, 6), "percentile": ev["percentile"], "p": ev["p_value"],
                    "wf_first": round(wf1, 6), "wf_second": round(wf2, 6), "verdict": verdict,
                    "data_quality": "real KRX PIT, 포트레벨(상관보정)", "note": "풀링 n=49057 상관뻥튀기 → 포트레벨 재검"})


if __name__ == "__main__":
    main()
