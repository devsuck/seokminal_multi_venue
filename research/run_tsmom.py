"""선물 멀티에셋 TSMOM 판정 (고정 파라미터).

질문: 12개월 모멘텀 타이밍이 vol-targeted 롱(buyhold)·랜덤·현금을 비용 후 이기는가?
베이스라인: random same-frequency 분포 + buy&hold + cash. walk-forward. Sharpe 기준.

실행: PYTHONPATH=. python3 research/run_tsmom.py
"""
from __future__ import annotations

import glob
import os
import random as _random

from research.backtest.portfolio_backtester import run_portfolio, portfolio_metrics
from research.validation.baselines import empirical_p_value
from research.hypotheses.tsmom import build_panel, tsmom_weights, buyhold_weights, random_weights
from research.hypotheses.tsmom import DEFAULTS
from research.data.futures_loader import BASKET
from research.agents.experiment_registry import log_experiment

N_RUNS = 200
SEED = 42
COST_BPS = 2.0
REBAL = 21  # 월 리밸런스


def _panels():
    syms = [s for s, _ in BASKET]
    out = {}
    for s in syms:
        pn = build_panel(s)
        if len(pn["dates"]) > DEFAULTS["lookback"] + DEFAULTS["vol_window"] + 30:
            out[s] = pn
    return out


def _filter(panels, lo, hi):
    out = {}
    for a, pn in panels.items():
        ds = [d for d in pn["dates"] if lo <= d < hi]
        if len(ds) > DEFAULTS["lookback"] + DEFAULTS["vol_window"] + 10:
            out[a] = {"symbol": a, "dates": ds, "close": {d: pn["close"][d] for d in ds}}
    return out


def main():
    panels = _panels()
    print("=" * 74)
    print(f"FUTURES TSMOM | {len(panels)} markets: {', '.join(panels)} | 고정 파라미터")
    print(f"lookback={DEFAULTS['lookback']}d target_vol={DEFAULTS['target_vol']} rebal={REBAL}d cost={COST_BPS}bps")
    print("=" * 74)

    strat = run_portfolio(panels, tsmom_weights, {}, COST_BPS, REBAL)
    sm = strat["metrics"]
    bh = run_portfolio(panels, buyhold_weights, {}, COST_BPS, REBAL)["metrics"]

    # random 분포 (sharpe)
    rand_sharpes = []
    for k in range(N_RUNS):
        rng = _random.Random(SEED + k)
        m = run_portfolio(panels, random_weights, {}, COST_BPS, REBAL, rng=rng)["metrics"]
        if m["sharpe"] is not None:
            rand_sharpes.append(m["sharpe"])
    pv = empirical_p_value(sm["sharpe"] or -99, rand_sharpes)

    # walk-forward
    all_dates = sorted(set().union(*[set(p["dates"]) for p in panels.values()]))
    mid = all_dates[len(all_dates) // 2]
    fh = run_portfolio(_filter(panels, all_dates[0], mid), tsmom_weights, {}, COST_BPS, REBAL)["metrics"]
    sh = run_portfolio(_filter(panels, mid, all_dates[-1] + "~"), tsmom_weights, {}, COST_BPS, REBAL)["metrics"]

    print(f"\nTSMOM  : ann_ret={sm['ann_return']} vol={sm['ann_vol']} SHARPE={sm['sharpe']} "
          f"maxDD={sm['max_drawdown']} days={sm['days']}")
    print(f"buyhold: ann_ret={bh['ann_return']} SHARPE={bh['sharpe']}")
    print(f"cash   : 0")
    print(f"vs random: sharpe pct={pv['percentile']} p={pv['p_value']} "
          f"(rand median sharpe={pv['random_median']}, n={len(rand_sharpes)})")
    print(f"walk-forward: 전반 sharpe={fh['sharpe']} / 후반 sharpe={sh['sharpe']}")

    passed = (sm["sharpe"] and sm["sharpe"] > 0 and (pv["percentile"] or 0) >= 95
              and (pv["p_value"] or 1) < 0.05 and (fh["sharpe"] or -9) > 0 and (sh["sharpe"] or -9) > 0
              and sm["sharpe"] > (bh["sharpe"] or -9))
    verdict = ("EDGE 후보 — random 95pct 초과 + WF 양쪽 + buyhold 초과" if passed
               else "REJECT — 기준 미달")
    if sm["underpowered"]:
        verdict = "UNDERPOWERED — " + verdict
    print(f"\nVERDICT: {verdict}")

    log_experiment({"hypothesis_id": "futures_tsmom", "tf": "1d", "rebalance": "monthly",
                    "status": "candidate" if passed else "rejected",
                    "sharpe": sm["sharpe"], "ann_return": sm["ann_return"], "max_drawdown": sm["max_drawdown"],
                    "buyhold_sharpe": bh["sharpe"], "random_percentile": pv["percentile"], "p": pv["p_value"],
                    "wf_first_sharpe": fh["sharpe"], "wf_second_sharpe": sh["sharpe"],
                    "n_markets": len(panels), "verdict": verdict, "note": "fixed params, no tuning"})


if __name__ == "__main__":
    main()
