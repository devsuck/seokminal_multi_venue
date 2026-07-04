"""US 오버나잇 갭 되메움 실검증 — 마지막 미검증 price 후보.

가설: 시가가 전일종가 대비 크게 하락갭 → 당일 되메움(반전) → 시가매수·종가청산 수익.
gap_continuation(지속, REJECT)의 반대방향. US 15m→일 시가/종가. 매칭 random(전일 종가매수 근사).
실행: PYTHONPATH=. python3 research/run_us_gapfill.py
"""
from __future__ import annotations

import glob
import os
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.intraday_store import load_df
from research.validation.baselines import empirical_p_value

GAP_THRESH = -0.005     # 하락갭 -0.5% 이하
COST_RT = 5 / 1e4       # US 대형 왕복 5bps
N_RUNS = 500
SEED = 42


def _daily_oc(sym: str):
    """15m → 일별 (open=첫봉시가, close=막봉종가, prev_close)."""
    df = load_df(sym, "15m")
    if len(df) < 2000:
        return None
    import datetime as dt
    days = {}
    for ts, o, c in zip(df["ts_utc"].tolist(), df["open"].tolist(), df["close"].tolist()):
        d = dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).strftime("%Y-%m-%d")
        if d not in days:
            days[d] = {"open": o, "close": c}
        else:
            days[d]["close"] = c
    ds = sorted(days)
    opens = [days[d]["open"] for d in ds]
    closes = [days[d]["close"] for d in ds]
    return opens, closes


def main():
    print("US 오버나잇 갭 되메움(하락갭 시가매수·종가청산) 실검증")
    syms = [os.path.basename(p).replace("_15m.parquet", "") for p in sorted(glob.glob("data/intraday/*_15m.parquet"))]
    strat, per_sym = [], []
    for sym in syms:
        oc = _daily_oc(sym)
        if oc is None:
            continue
        opens, closes = oc
        # 진입일 = 하락갭(open/prev_close-1 <= thresh). 수익 = 당일 open→close.
        ents, elig = [], []
        for i in range(1, len(opens)):
            if opens[i] <= 0 or closes[i - 1] <= 0:
                continue
            elig.append(i)
            if opens[i] / closes[i - 1] - 1 <= GAP_THRESH:
                ents.append(i)
        rets = [closes[i] / opens[i] - 1 - COST_RT for i in ents]
        strat += rets
        per_sym.append((opens, closes, len(ents), elig))
    n = len(strat)
    if n < 30:
        print(f"진입 {n} 부족"); return
    smean = _st.mean(strat)
    rng = _random.Random(SEED); rmeans = []
    for _ in range(N_RUNS):
        pool = []
        for opens, closes, k, elig in per_sym:
            if k == 0 or not elig:
                continue
            for i in rng.sample(elig, min(k, len(elig))):
                pool.append(closes[i] / opens[i] - 1 - COST_RT)
        rmeans.append(_st.mean(pool) if pool else 0.0)
    ev = empirical_p_value(smean, rmeans)
    mid = n // 2
    wf1, wf2 = _st.mean(strat[:mid]), _st.mean(strat[mid:])
    print(f"\n진입 {n} (하락갭≤{GAP_THRESH:.1%}) | 평균 당일수익 {smean:+.4%}")
    print(f"vs random(당일 open→close): pct={ev['percentile']} p={ev['p_value']} (med={ev['random_median']:+.4%})")
    print(f"walk-forward: 전반 {wf1:+.4%} / 후반 {wf2:+.4%}")
    pct = ev["percentile"] or 0.0
    passed = smean > 0 and pct >= 95 and (ev["p_value"] or 1) < 0.05 and wf1 > 0 and wf2 > 0
    verdict = ("EDGE 후보 — 갭되메움 통과" if passed else
               "WEAK — random 80~95pct" if smean > 0 and pct >= 80 else "REJECT — 갭되메움 엣지 없음")
    print(f"\nVERDICT: {verdict}")
    log_experiment({"hypothesis_id": "us_overnight_gap_fill_v1_REAL",
                    "status": "candidate" if passed else "weak" if (smean > 0 and pct >= 80) else "rejected",
                    "n": n, "mean_return": round(smean, 6), "percentile": ev["percentile"], "p": ev["p_value"],
                    "wf_first": round(wf1, 6), "wf_second": round(wf2, 6),
                    "data_quality": "real US 15m→daily", "verdict": verdict,
                    "note": "하락갭 시가매수 종가청산, 고정파라미터"})


if __name__ == "__main__":
    main()
