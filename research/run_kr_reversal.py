"""KR 단기 반전 실검증 — 모멘텀 실패의 거울상.

순수 모멘텀이 KR서 랜덤보다 나빴음(소형주 반전 강함 시사) → 반대(단기 반전) 테스트.
주간 리밸: 과거 5일 최대낙폭(하위decile) 롱, 5일 보유. 매칭 random decile. PIT survivorship-free.
실행: PYTHONPATH=. python3 research/run_kr_reversal.py
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

LOOKBACK = 5          # 과거 5거래일 수익으로 랭크
REBAL = 5             # 주간(5거래일) 리밸
COST_RT = 40 / 1e4    # 왕복 40bps(주간 턴오버 높음)
N_RUNS = 500
SEED = 42


def main():
    print("KR 단기반전(5일 낙폭 → 하위decile 롱, 주간 리밸) 실검증 — PIT survivorship-free")
    s = build_series("KOSDAQ", min_bars=200)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=200))
    all_dates = sorted(set().union(*[set(b["dates"]) for b in s.values()]))
    rebal = all_dates[LOOKBACK + 5::REBAL]
    print(f"종목 {len(s)} | 거래일 {len(all_dates)} | 리밸 {len(rebal)}회")

    def at(b, d):
        j = bisect.bisect_right(b["dates"], d) - 1
        return j if j >= 0 else None

    def universe(t):
        u = []
        for b in s.values():
            k = at(b, t)
            if k is None or k < 20:
                continue
            if _st.mean(b["tval"][k - 20:k]) < 1e9 or b["marcap"][k] < 5e10:
                continue
            p0, pl = b["close"][k], b["close"][k - LOOKBACK]
            if p0 <= 0 or pl <= 0:
                continue
            u.append((b, k, p0 / pl - 1))     # 과거 5일 수익(작을수록 낙폭 큼)
        return u

    port, rng = [], _random.Random(SEED)
    rand_series = [[] for _ in range(N_RUNS)]
    for ri in range(len(rebal) - 1):
        t, tn = rebal[ri], rebal[ri + 1]
        u = universe(t)
        if len(u) < 30:
            continue
        u.sort(key=lambda x: x[2])            # 수익 오름차순 = 낙폭 큰 순
        n_top = max(5, len(u) // 10)

        def fwd(sub):
            rs = []
            for b, k, _ in sub:
                kn = at(b, tn)
                rs.append((b["close"][kn] / b["close"][k] - 1 - COST_RT) if (kn and kn > k) else -COST_RT)
            return _st.mean(rs) if rs else 0.0

        port.append(fwd(u[:n_top]))           # 하위decile(최대낙폭) 롱
        for run in range(N_RUNS):
            rand_series[run].append(fwd(rng.sample(u, n_top)))

    if len(port) < 20:
        print(f"리밸 {len(port)} — 데이터부족"); return
    wk = _st.mean(port)
    ann = (1 + wk) ** 52 - 1
    rand_wk = [_st.mean(r) for r in rand_series]
    ev = empirical_p_value(wk, rand_wk)
    mid = len(port) // 2
    wf1, wf2 = _st.mean(port[:mid]), _st.mean(port[mid:])
    print(f"\n리밸 {len(port)} | 주평균 {wk:+.4%} (연율 {ann:+.2%})")
    print(f"vs random decile: pct={ev['percentile']} p={ev['p_value']} (rand_med={ev['random_median']:+.4%})")
    print(f"walk-forward(주평균): 전반 {wf1:+.4%} / 후반 {wf2:+.4%}")

    pct = ev["percentile"] or 0.0
    passed = wk > 0 and pct >= 95 and (ev["p_value"] or 1) < 0.05 and wf1 > 0 and wf2 > 0
    verdict = ("EDGE 후보 — 단기반전 random·비용후 통과" if passed else
               "WEAK — random 80~95pct" if wk > 0 and pct >= 80 else
               "REJECT — 비용후 반전엣지 없음")
    print(f"\nVERDICT: {verdict}")
    log_experiment({"hypothesis_id": "kr_short_term_reversal_v1_REAL",
                    "status": "candidate" if passed else "weak" if (wk > 0 and pct >= 80) else "rejected",
                    "n_rebal": len(port), "week_mean": round(wk, 6), "ann": round(ann, 6),
                    "percentile": ev["percentile"], "p": ev["p_value"], "wf_first": round(wf1, 6), "wf_second": round(wf2, 6),
                    "data_quality": "real KRX PIT survivorship-free", "verdict": verdict,
                    "note": "주간 5일반전 하위decile 롱, 고정파라미터, 왕복40bps"})


if __name__ == "__main__":
    main()
