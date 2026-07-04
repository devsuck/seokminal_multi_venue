"""크립토 크로스섹셔널 모멘텀 실검증 — KR과 다른 자산군.

KR 소형주 모멘텀은 죽었지만 크립토 XS 모멘텀은 역사적으로 문서화된 효과. 정직한 확인.
주간 리밸: 30일 상대강도 상위 quantile 롱, 7일 보유. 매칭 random. HL 일봉.
실행: PYTHONPATH=. python3 research/run_crypto_momentum.py
"""
from __future__ import annotations

import glob
import os
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.intraday_store import load_df
from research.validation.baselines import empirical_p_value

FUTURES = {"ES", "NQ", "YM", "RTY", "CL", "GC", "SI", "HG", "NG", "ZB", "ZN", "ZF", "ZT",
           "ZC", "ZS", "ZW", "ZL", "ZM", "ZQ", "UB", "HE", "LE", "PA", "PL", "KC", "SB",
           "CC", "CT", "HO", "RB", "EMD", "NKD"}
LOOKBACK = 30
REBAL = 7
COST_RT = 10 / 1e4
N_RUNS = 500
SEED = 42


def _coins():
    out = {}
    for p in sorted(glob.glob("data/intraday/*_1d.parquet")):
        sym = os.path.basename(p).replace("_1d.parquet", "")
        if sym in FUTURES:
            continue
        df = load_df(sym, "1d")
        if len(df) < 200:
            continue
        out[sym] = df["close"].tolist()
    return out


def main():
    print("크립토 크로스섹셔널 모멘텀(30일 상위 quantile 롱, 주간 리밸) 실검증")
    coins = _coins()
    n = min(len(c) for c in coins.values())
    n = max(len(c) for c in coins.values())
    maxlen = max(len(c) for c in coins.values())
    print(f"코인 {len(coins)} | 최대 {maxlen}일")

    # 공통 인덱스축(뒤 정렬 가정: 최근이 끝). 인덱스 기준 리밸.
    rebal = list(range(LOOKBACK + 1, maxlen - REBAL, REBAL))
    port, rng = [], _random.Random(SEED)
    rand_series = [[] for _ in range(N_RUNS)]
    for t in rebal:
        u = []
        for sym, c in coins.items():
            if t >= len(c) or t - LOOKBACK < 0 or t + REBAL >= len(c):
                continue
            p0, pl = c[t], c[t - LOOKBACK]
            if p0 <= 0 or pl <= 0:
                continue
            u.append((sym, c, t, p0 / pl - 1))     # 30일 수익
        if len(u) < 8:
            continue
        u.sort(key=lambda x: -x[3])                # 수익 내림차순 = 강한 순
        n_top = max(2, len(u) // 5)                # 상위 20%

        def fwd(sub):
            rs = [c[t + REBAL] / c[t] - 1 - COST_RT for _, c, t, _ in sub if c[t] > 0]
            return _st.mean(rs) if rs else 0.0

        port.append(fwd(u[:n_top]))
        for run in range(N_RUNS):
            rand_series[run].append(fwd(rng.sample(u, n_top)))

    if len(port) < 20:
        print(f"리밸 {len(port)} 부족"); return
    wk = _st.mean(port)
    ann = (1 + wk) ** 52 - 1
    rand_wk = [_st.mean(r) for r in rand_series]
    ev = empirical_p_value(wk, rand_wk)
    mid = len(port) // 2
    wf1, wf2 = _st.mean(port[:mid]), _st.mean(port[mid:])
    print(f"\n리밸 {len(port)} | 주평균 {wk:+.4%} (연율 {ann:+.2%})")
    print(f"vs random: pct={ev['percentile']} p={ev['p_value']} (rand_med={ev['random_median']:+.4%})")
    print(f"walk-forward: 전반 {wf1:+.4%} / 후반 {wf2:+.4%}")

    pct = ev["percentile"] or 0.0
    passed = wk > 0 and pct >= 95 and (ev["p_value"] or 1) < 0.05 and wf1 > 0 and wf2 > 0
    verdict = ("EDGE 후보 — 크립토 XS 모멘텀 통과" if passed else
               "WEAK — random 80~95pct" if wk > 0 and pct >= 80 else
               "REJECT — 비용후 엣지 없음")
    print(f"\nVERDICT: {verdict}")
    log_experiment({"hypothesis_id": "crypto_xs_momentum_weekly_v1_REAL",
                    "status": "candidate" if passed else "weak" if (wk > 0 and pct >= 80) else "rejected",
                    "n_rebal": len(port), "week_mean": round(wk, 6), "ann": round(ann, 6),
                    "percentile": ev["percentile"], "p": ev["p_value"], "wf_first": round(wf1, 6), "wf_second": round(wf2, 6),
                    "data_quality": "real HL daily (~25 coins)", "verdict": verdict,
                    "note": "주간 30일 XS 모멘텀 상위20% 롱, 고정파라미터, 왕복10bps. 크립토 유니버스 생존편향 주의(현존 코인)"})


if __name__ == "__main__":
    main()
