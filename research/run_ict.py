"""ICT Model A 검증 — 실 15분봉(US) 다종목 풀링. "ICT가 random 이기냐" 정직한 첫 답.

각 종목: NY 킬존 sweep+FVG 롱 진입 → H봉 보유 per-trade 수익. 전 종목 풀링.
매칭 random = 각 종목 킬존 eligible에서 동일 진입수 랜덤, 풀링. empirical p-value.
실행: PYTHONPATH=. python3 research/run_ict.py
"""
from __future__ import annotations

import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.intraday_store import load_df
from research.ict.strategy import model_a_entries
from research.validation.baselines import empirical_p_value

SYMBOLS = ["AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL", "TSLA", "SPY", "JPM", "XLK", "AMD", "NFLX"]
HOLD = 8
COST_RT = 10.0 / 10_000.0   # 왕복 10bps(편도 5)
N_RUNS = 500
SEED = 42


def _bars(sym: str) -> dict | None:
    df = load_df(sym, "15m")
    if len(df) < 500:
        return None
    return {"ts": df["ts_utc"].tolist(), "o": df["open"].tolist(), "h": df["high"].tolist(),
            "l": df["low"].tolist(), "c": df["close"].tolist()}


def main():
    print("=" * 76)
    print("ICT Model A (killzone sweep+FVG long) — 실 15분봉 US 풀링 검증")
    print("=" * 76)
    per_symbol = []
    strat_rets = []          # 전 종목 per-trade 수익 풀
    sym_data = []            # (closes, entries, eligible) 랜덤용
    for sym in SYMBOLS:
        bars = _bars(sym)
        if bars is None:
            continue
        c = bars["c"]
        sig = model_a_entries(bars)
        entries = [i for i in sig["entries"] if i + HOLD < len(c)]
        eligible = [i for i in sig["eligible"] if i + HOLD < len(c)]
        rets = [c[i + HOLD] / c[i] - 1 - COST_RT for i in entries]
        per_symbol.append((sym, len(entries), _st.mean(rets) if rets else None))
        strat_rets += rets
        sym_data.append((c, len(entries), eligible))
        print(f"  {sym:6} 진입 {len(entries):4}  평균수익 {(_st.mean(rets) if rets else 0):+.4%}  "
              f"(FVG {sig['n_fvg']} sweep {sig['n_sweep']} kz {sig['n_kz']})")

    n_tr = len(strat_rets)
    if n_tr < 30:
        print(f"\n총 진입 {n_tr} — UNDERPOWERED"); return
    strat_mean = _st.mean(strat_rets)

    # 매칭 random(풀링): 각 종목 eligible에서 동일 진입수 랜덤 → 수익 풀 평균
    rng = _random.Random(SEED)
    rand_means = []
    for _ in range(N_RUNS):
        pool = []
        for c, k, elig in sym_data:
            if k == 0 or not elig:
                continue
            picks = rng.sample(elig, min(k, len(elig)))
            pool += [c[i + HOLD] / c[i] - 1 - COST_RT for i in picks]
        rand_means.append(_st.mean(pool) if pool else 0.0)
    ev = empirical_p_value(strat_mean, rand_means)

    mid = n_tr // 2
    wf1, wf2 = _st.mean(strat_rets[:mid]), _st.mean(strat_rets[mid:])
    print(f"\n총 진입 {n_tr} | 전략 평균수익 {strat_mean:+.4%}")
    print(f"vs 매칭 random: percentile={ev['percentile']} p={ev['p_value']} (rand_med={ev['random_median']:+.4%})")
    print(f"walk-forward: 전반 {wf1:+.4%} / 후반 {wf2:+.4%}")

    pct = ev["percentile"] or 0.0
    passed = strat_mean > 0 and pct >= 95 and (ev["p_value"] or 1) < 0.05 and wf1 > 0 and wf2 > 0
    verdict = ("EDGE 후보 — random·비용후 통과(재현·강건성 추가검증 필요)" if passed else
               "WEAK — random 80~95pct" if strat_mean > 0 and pct >= 80 else
               "REJECT — 매칭 random·비용 못 넘음 (ICT Model A 엣지 없음)")
    print(f"\nVERDICT: {verdict}")
    print("데이터: 실 15분봉 US. 킬존=UTC 13:30-15:00 근사(DST). 연구전용, live 아님.")

    log_experiment({"hypothesis_id": "ict_model_a_killzone_sweep_fvg_v1",
                    "status": "candidate" if passed else "weak" if (strat_mean > 0 and pct >= 80) else "rejected",
                    "n_trades": n_tr, "mean_return": round(strat_mean, 6), "percentile": ev["percentile"],
                    "p": ev["p_value"], "wf_first": round(wf1, 6), "wf_second": round(wf2, 6),
                    "symbols": len(sym_data), "hold_bars": HOLD,
                    "data_quality": "real 15m US intraday (IB)", "verdict": verdict,
                    "note": "ICT 객관 프리미티브 조합(killzone+bullish sweep+bullish FVG) 고정파라미터"})


if __name__ == "__main__":
    main()
