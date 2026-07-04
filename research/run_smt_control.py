"""SMT 정직 통제 — confound 제거. SMT저점 vs 일반 스윙저점(둘 다 딥매수).

SMT가 random(아무봉) 이긴 게 '다이버전스'인가 '저점 진입'인가?
통제: 매칭 baseline = 같은 종목 **스윙저점**(다이버전스 없는)에서 랜덤. 둘 다 딥매수.
SMT가 일반저점도 이기면 → 다이버전스 진짜. 아니면 → 그냥 인트라데이 딥반등.
실행: PYTHONPATH=. python3 research/run_smt_control.py
"""
from __future__ import annotations

import glob
import os
import random as _random
import statistics as _st

from research.ict.primitives import killzone_indices, swings
from research.run_ict_2024 import COST_RT, N_RUNS, SEED, _bars, _sameday_ret
from research.run_ict_final import _smt_entries
from research.validation.baselines import empirical_p_value


def main():
    print("SMT 통제 — SMT저점 vs 일반 스윙저점(둘 다 딥매수). 다이버전스만의 효과?")
    syms = [os.path.basename(p).replace("_15m.parquet", "") for p in sorted(glob.glob("data/intraday/*_15m.parquet"))]
    syms = [s for s in syms if not s.startswith("XL")][:14]
    data = {s: _bars(s) for s in syms}
    data = {s: b for s, b in data.items() if b}
    ref = data.get("SPY") or next(iter(data.values()))
    ref_close = {ref["ts"][i]: ref["c"][i] for i in range(len(ref["c"]))}

    smt_rets, per_sym = [], []
    all_low_rets = []
    for s, b in data.items():
        kzs = set(killzone_indices(b["ts"]))
        # 모든 스윙저점(킬존, 당일청산 가능) = 통제 풀
        lows = [i for i in swings(b["h"], b["l"], k=2)["lows"] if i in kzs and b["exit"][i] > i]
        smt = [i for i in _smt_entries(b, ref_close) if b["exit"][i] > i]
        smt_rets += _sameday_ret(b["c"], b["exit"], smt)
        all_low_rets += _sameday_ret(b["c"], b["exit"], lows)
        if smt:
            per_sym.append((b["c"], b["exit"], len(smt), lows))

    print(f"\nSMT 저점 진입 {len(smt_rets)}건 당일 {_st.mean(smt_rets):+.4%}")
    print(f"일반 스윙저점 {len(all_low_rets)}건 당일 {_st.mean(all_low_rets):+.4%}  (딥매수 기저효과)")

    # 매칭 random = 같은 종목 스윙저점에서 랜덤(다이버전스 없는 딥매수)
    rng = _random.Random(SEED); rmeans = []
    for _ in range(N_RUNS):
        pool = []
        for c, ex, k, lows in per_sym:
            if not lows:
                continue
            for i in rng.sample(lows, min(k, len(lows))):
                if c[i] > 0:
                    pool.append(c[ex[i]] / c[i] - 1 - COST_RT)
        rmeans.append(_st.mean(pool) if pool else 0.0)
    ev = empirical_p_value(_st.mean(smt_rets), rmeans)
    print(f"\nSMT vs 일반저점-random: pct={ev['percentile']} p={ev['p_value']} (med={ev['random_median']:+.4%})")

    diverg_real = (ev["percentile"] or 0) >= 95 and (ev["p_value"] or 1) < 0.05
    print(f"\nVERDICT: {'다이버전스 진짜 — 저점기저 넘어 SMT 고유엣지' if diverg_real else 'REJECT — SMT엣지=그냥 인트라데이 딥반등(다이버전스 무의미). confound였음'}")

    from research.agents.experiment_registry import log_experiment
    log_experiment({"hypothesis_id": "ict_smt_controlled", "status": "candidate" if diverg_real else "rejected",
                    "smt_ret": round(_st.mean(smt_rets), 6), "all_low_ret": round(_st.mean(all_low_rets), 6),
                    "percentile": ev["percentile"], "p": ev["p_value"],
                    "data_quality": "real US 15m, 스윙저점 통제", "verdict": "SMT confound 통제(저점기저 제거)",
                    "note": "SMT vs 일반스윙저점. 다이버전스 고유효과 검정"})


if __name__ == "__main__":
    main()
