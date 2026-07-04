"""ICT 최종 — 전 모델 통합 BH-FDR. 마지막 사망확인 후 ICT 졸업.

MODELS(2024·silver·OTE·unicorn·iFVG·CISD) + SMT(SPY 상관 다이버전스). 당일청산 단타.
전부 한 BH-FDR로 묶음 = cherry-pick 방지. 실행: PYTHONPATH=. python3 research/run_ict_final.py
"""
from __future__ import annotations

import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.ict.models_2024 import MODELS
from research.ict.primitives import killzone_indices, swings
from research.run_ict_2024 import COST_RT, N_RUNS, SEED, _bars, _sameday_ret
from research.validation.baselines import empirical_p_value
from research.validation.multiple_testing import benjamini_hochberg
import glob, os


def _smt_entries(b, ref_close):
    """SMT: 종목이 lower-low인데 SPY는 higher-low(다이버전스) → 롱 진입."""
    l, ts = b["l"], b["ts"]
    lows = swings(b["h"], l, k=2)["lows"]
    kzs = set(killzone_indices(ts))
    ent = []
    for a, cur in zip(lows, lows[1:]):
        if l[cur] < l[a]:  # 종목 lower low
            ra, rc = ref_close.get(ts[a]), ref_close.get(ts[cur])
            if ra and rc and rc > ra and cur in kzs:  # SPY는 higher(다이버전스)
                ent.append(cur)
    return ent


def _eval(strat, per_sym):
    n = len(strat)
    if n < 30:
        return {"n": n, "mean": None, "pct": None, "p": None, "wf1": None, "wf2": None}
    smean = _st.mean(strat)
    rng = _random.Random(SEED); rmeans = []
    for _ in range(N_RUNS):
        pool = []
        for c, ex, k, kz in per_sym:
            if not kz:
                continue
            for i in rng.sample(kz, min(k, len(kz))):
                if c[i] > 0:
                    pool.append(c[ex[i]] / c[i] - 1 - COST_RT)
        rmeans.append(_st.mean(pool) if pool else 0.0)
    ev = empirical_p_value(smean, rmeans)
    mid = n // 2
    return {"n": n, "mean": round(smean, 6), "pct": ev["percentile"], "p": ev["p_value"],
            "wf1": round(_st.mean(strat[:mid]), 6), "wf2": round(_st.mean(strat[mid:]), 6)}


def main():
    print("=" * 72)
    print("ICT 최종 통합 검증 (전 모델 + SMT, 단일 BH-FDR) → 졸업")
    print("=" * 72)
    syms = [os.path.basename(p).replace("_15m.parquet", "") for p in sorted(glob.glob("data/intraday/*_15m.parquet"))]
    syms = [s for s in syms if not s.startswith("XL")][:14]
    data = {s: _bars(s) for s in syms}
    data = {s: b for s, b in data.items() if b}
    ref = data.get("SPY") or next(iter(data.values()))
    ref_close = {ref["ts"][i]: ref["c"][i] for i in range(len(ref["c"]))}
    print(f"종목 {len(data)} (SMT 기준=SPY)\n")

    results = {}
    for name, fn in MODELS.items():
        strat, per_sym = [], []
        for s, b in data.items():
            ent = [i for i in fn(b) if b["exit"][i] > i]
            strat += _sameday_ret(b["c"], b["exit"], ent)
            if ent:
                kz = [i for i in killzone_indices(b["ts"]) if b["exit"][i] > i]
                per_sym.append((b["c"], b["exit"], len([x for x in ent]), kz))
        results[name] = _eval(strat, per_sym)

    # SMT
    strat, per_sym = [], []
    for s, b in data.items():
        ent = [i for i in _smt_entries(b, ref_close) if b["exit"][i] > i]
        strat += _sameday_ret(b["c"], b["exit"], ent)
        if ent:
            kz = [i for i in killzone_indices(b["ts"]) if b["exit"][i] > i]
            per_sym.append((b["c"], b["exit"], len(ent), kz))
    results["ict_smt"] = _eval(strat, per_sym)

    for name, v in results.items():
        m = f"{v['mean']:+.4%}" if v["mean"] is not None else "—"
        print(f"  {name:20} n={v['n']:5} 당일 {m:>9} pct={v['pct']} p={v['p']}")

    ids = [k for k, v in results.items() if v["p"] is not None]
    pvals = [results[k]["p"] for k in ids]
    bh = benjamini_hochberg(pvals, alpha=0.1)
    print("\n" + "-" * 72)
    print(f"통합 BH-FDR(α=0.1, {len(pvals)}개 모델): 생존 {bh['n_survivors']}/{len(pvals)}")
    for i, k in enumerate(ids):
        print(f"  {k:20} p={pvals[i]} survivor={bh['survivors'][i]}")
    print(f"\nVERDICT: {'생존 모델 있음 — 추가검증' if bh['n_survivors'] > 0 else 'REJECT 전멸 — ICT 기계화 엣지 없음. ICT 졸업.'}")

    for k, v in results.items():
        log_experiment({"hypothesis_id": f"{k}_final", "status": "rejected" if v["mean"] is not None else "underpowered",
                        "n": v["n"], "mean_return": v["mean"], "percentile": v["pct"], "p": v["p"],
                        "data_quality": "real US 15m 당일청산", "verdict": "ICT 통합 BH-FDR 졸업검증",
                        "note": "ICT 공개개념 기계화 최종. 전 모델 단일 BH-FDR"})


if __name__ == "__main__":
    main()
