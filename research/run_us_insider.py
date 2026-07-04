"""① US 내부자 매수(Form 4) 이벤트 스터디 — buyback 엣지의 US 교차검증.

가설: 내부자(임원)가 자기 주식 오픈마켓 매수 = 경영진 신뢰 신호(buyback과 같은 family).
US 15m→일봉 유니버스(~30 대형주) Form 4 매수(code P) → 익일 진입 20일 보유 vs random.
⚠️ 대형주는 내부자가 주로 매도 → 매수 이벤트 적을 수 있음(underpowered 가능).
실행: PYTHONPATH=. python3 research/run_us_insider.py
"""
from __future__ import annotations

import datetime as _dt
import glob
import os
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.intraday_store import load_df
from research.validation.baselines import empirical_p_value
from insider.edgar_client import get_form4_transactions

HOLD = 20
COST_RT = 5 / 1e4
N_RUNS = 500
SEED = 42


def _daily(sym):
    df = load_df(sym, "15m")
    if len(df) < 2000:
        return None
    days = {}
    for ts, c in zip(df["ts_utc"].tolist(), df["close"].tolist()):
        d = _dt.datetime.fromtimestamp(int(ts), tz=_dt.timezone.utc).strftime("%Y-%m-%d")
        days[d] = c
    ds = sorted(days)
    return ds, [days[d] for d in ds]


def main():
    print("=" * 70)
    print("① US 내부자 매수(Form 4) 이벤트 — buyback 엣지 US 교차검증")
    print("=" * 70)
    syms = [os.path.basename(p).replace("_15m.parquet", "") for p in sorted(glob.glob("data/intraday/*_15m.parquet"))]
    syms = [s for s in syms if not s.startswith("XL")]  # ETF 제외

    strat, per_sym, total_buys = [], [], 0
    for sym in syms:
        dd = _daily(sym)
        if dd is None:
            continue
        ds, cl = dd
        try:
            txns = get_form4_transactions(sym, days=900)
        except Exception:
            continue
        buys = [t for t in txns if t.get("trade_type") == "BUY" or t.get("transaction_code") == "P"]
        total_buys += len(buys)
        import bisect
        ents = []
        for t in buys:
            td = t.get("transaction_date")
            if not td:
                continue
            j = bisect.bisect_right(ds, td)  # 익일
            if 0 < j < len(ds) - HOLD:
                ents.append(j)
        rets = [cl[i + HOLD] / cl[i] - 1 - COST_RT for i in ents if cl[i] > 0]
        strat += rets
        if ents:
            per_sym.append((cl, len(ents)))
        print(f"  {sym:6} 매수이벤트 {len(buys):3} 유효진입 {len(ents):3}")

    print(f"\n총 내부자매수 {total_buys} | 유효 진입 {len(strat)}")
    if len(strat) < 30:
        print("VERDICT: UNDERPOWERED — 대형주 내부자매수 이벤트 부족(넓은 유니버스 필요)")
        log_experiment({"hypothesis_id": "us_insider_buy_v1", "status": "underpowered",
                        "n": len(strat), "verdict": "US 대형주 내부자매수 이벤트 <30 = underpowered",
                        "data_quality": "SEC Form4 + US 15m", "note": "buyback US교차검증. 소형주 유니버스 필요"})
        return
    smean = _st.mean(strat)
    rng = _random.Random(SEED); rmeans = []
    for _ in range(N_RUNS):
        pool = []
        for cl, k in per_sym:
            elig = list(range(len(cl) - HOLD))
            for i in rng.sample(elig, min(k, len(elig))):
                pool.append(cl[i + HOLD] / cl[i] - 1 - COST_RT)
        rmeans.append(_st.mean(pool) if pool else 0.0)
    ev = empirical_p_value(smean, rmeans)
    mid = len(strat) // 2
    wf1, wf2 = _st.mean(strat[:mid]), _st.mean(strat[mid:])
    print(f"평균수익 {smean:+.4%} | vs random pct={ev['percentile']} p={ev['p_value']} (med={ev['random_median']:+.4%})")
    print(f"walk-forward: 전반 {wf1:+.4%} / 후반 {wf2:+.4%}")
    pct = ev["percentile"] or 0.0
    passed = smean > 0 and pct >= 95 and (ev["p_value"] or 1) < 0.05 and wf1 > 0 and wf2 > 0
    verdict = ("EDGE 후보 — US 내부자매수 = buyback 교차확증" if passed else
               "WEAK — random 80~95pct" if smean > 0 and pct >= 80 else "REJECT — US 내부자매수 엣지 없음")
    print(f"\nVERDICT: {verdict}")
    log_experiment({"hypothesis_id": "us_insider_buy_v1", "status": "candidate" if passed else "weak" if (smean>0 and pct>=80) else "rejected",
                    "n": len(strat), "mean_return": round(smean, 6), "percentile": ev["percentile"], "p": ev["p_value"],
                    "wf_first": round(wf1, 6), "wf_second": round(wf2, 6),
                    "data_quality": "SEC Form4 + US 15m→daily(~30 대형주)", "verdict": verdict,
                    "note": "buyback(경영진 신뢰신호) US 교차검증. 대형주 한정=capacity 주의"})


if __name__ == "__main__":
    main()
