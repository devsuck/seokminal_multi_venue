"""ICT 2024 모델들 단타 검증 — 실 15분봉 US, 당일청산, BH-FDR 다중검정.

각 모델: 킬존 진입 → **같은 거래일 마지막 봉 청산**(단타). 매칭 random(킬존 eligible, 당일청산).
여러 ICT 모델 = 다중검정 → BH-FDR로 우연통과 방지. 단타 현실비용(왕복 10bps).
실행: PYTHONPATH=. python3 research/run_ict_2024.py
"""
from __future__ import annotations

import datetime as _dt
import glob
import os
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.intraday_store import load_df
from research.ict.models_2024 import MODELS
from research.validation.baselines import empirical_p_value
from research.validation.multiple_testing import benjamini_hochberg

COST_RT = 10 / 1e4     # 단타 왕복 10bps(유동 대형주)
N_RUNS = 500
SEED = 42


def _bars(sym):
    df = load_df(sym, "15m")
    if len(df) < 2000:
        return None
    ts = df["ts_utc"].tolist()
    dates = [_dt.datetime.fromtimestamp(int(t), tz=_dt.timezone.utc).strftime("%Y-%m-%d") for t in ts]
    # 각 봉 → 그날 마지막 봉 인덱스(당일청산 대상)
    last_of_day = {}
    for i, d in enumerate(dates):
        last_of_day[d] = i
    exit_idx = [last_of_day[dates[i]] for i in range(len(dates))]
    return {"ts": ts, "o": df["open"].tolist(), "h": df["high"].tolist(),
            "l": df["low"].tolist(), "c": df["close"].tolist(), "exit": exit_idx, "dates": dates}


def _sameday_ret(c, exit_idx, entries):
    out = []
    for i in entries:
        xi = exit_idx[i]
        if xi > i and c[i] > 0:
            out.append(c[xi] / c[i] - 1 - COST_RT)
    return out


def main():
    print("=" * 72)
    print("ICT 2024 모델 단타 검증 — 실 15분봉 US, 당일청산, BH-FDR")
    print("=" * 72)
    syms = [os.path.basename(p).replace("_15m.parquet", "") for p in sorted(glob.glob("data/intraday/*_15m.parquet"))]
    syms = [s for s in syms if not s.startswith("XL")][:14]
    data = {s: _bars(s) for s in syms}
    data = {s: b for s, b in data.items() if b}
    print(f"종목 {len(data)}\n")

    results = {}
    for name, fn in MODELS.items():
        strat, per_sym = [], []
        for s, b in data.items():
            ent = [i for i in fn(b) if b["exit"][i] > i]
            rets = _sameday_ret(b["c"], b["exit"], ent)
            strat += rets
            if ent:
                # 킬존 eligible(랜덤용): 당일청산 가능한 킬존 봉
                from research.ict.primitives import killzone_indices
                kz = [i for i in killzone_indices(b["ts"]) if b["exit"][i] > i]
                per_sym.append((b["c"], b["exit"], len(rets), kz))
        n = len(strat)
        if n < 30:
            results[name] = {"n": n, "mean": None, "pct": None, "p": None, "wf1": None, "wf2": None}
            print(f"  {name:20} n={n:4} UNDERPOWERED")
            continue
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
        results[name] = {"n": n, "mean": round(smean, 6), "pct": ev["percentile"], "p": ev["p_value"],
                         "wf1": round(_st.mean(strat[:mid]), 6), "wf2": round(_st.mean(strat[mid:]), 6)}
        print(f"  {name:20} n={n:4} 당일수익 {smean:+.4%} pct={ev['percentile']} p={ev['p_value']} wf={results[name]['wf1']:.4f}/{results[name]['wf2']:.4f}")

    # BH-FDR across models
    ids = [k for k, v in results.items() if v["p"] is not None]
    pvals = [results[k]["p"] for k in ids]
    print("\n" + "-" * 72)
    if pvals:
        bh = benjamini_hochberg(pvals, alpha=0.1)
        print(f"BH-FDR(다중검정 α=0.1): 생존 {bh['n_survivors']}/{len(pvals)}")
        for i, k in enumerate(ids):
            surv = bh["survivors"][i]
            print(f"  {k:20} p={pvals[i]} survivor={surv}")
    any_edge = any((results[k]["mean"] or 0) > 0 and (results[k]["pct"] or 0) >= 95 for k in ids)
    print(f"\nVERDICT: {'일부 EDGE 후보(강건성 추가검증 필요)' if any_edge else 'REJECT — ICT 2024 모델 단타 엣지 없음(비용후 랜덤)'}")

    for k, v in results.items():
        log_experiment({"hypothesis_id": f"{k}_daytrade_v1", "status": "candidate" if (v.get("mean") or 0) > 0 and (v.get("pct") or 0) >= 95 else "weak" if (v.get("mean") or 0) > 0 and (v.get("pct") or 0) >= 80 else "underpowered" if v["mean"] is None else "rejected",
                        "n": v["n"], "mean_return": v["mean"], "percentile": v["pct"], "p": v["p"],
                        "wf_first": v["wf1"], "wf_second": v["wf2"],
                        "data_quality": "real US 15m, 당일청산", "verdict": "ICT 2024 단타, BH-FDR 묶음",
                        "note": "ICT 공개개념 기계화. 당일청산 단타. 왕복10bps"})


if __name__ == "__main__":
    main()
