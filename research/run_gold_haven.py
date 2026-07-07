"""금(GC) 안전자산 가설 판정 (고정 파라미터).

질문: 실질금리 하락 레짐 게이트 + 리스크오프 부스트가 buyhold·랜덤·비용을 이기는가?
베이스라인: random same-frequency 분포 + buy&hold. walk-forward. Sharpe 기준.

실행: PYTHONPATH=. python3 research/run_gold_haven.py
"""
from __future__ import annotations

import random as _random

from research.backtest.portfolio_backtester import run_portfolio
from research.validation.baselines import empirical_p_value
from research.hypotheses.gold_haven import (
    DEFAULTS, gold_haven_weights, buyhold_weights, random_weights, build_macro_panel,
)
from research.hypotheses.tsmom import build_panel
from research.agents.experiment_registry import log_experiment

N_RUNS = 200
SEED = 42
COST_BASE_BPS = 2.0
COST_STRESS_BPS = 20.0
REBAL = 1  # 매일 체크


def _filter(panel: dict, lo: str, hi: str) -> dict:
    ds = [d for d in panel["dates"] if lo <= d < hi]
    return {"symbol": panel["symbol"], "dates": ds, "close": {d: panel["close"][d] for d in ds}}


def _filter_macro(macro: dict, lo: str, hi: str) -> dict:
    ds = [d for d in macro["dates"] if lo <= d < hi]
    return {
        "dates": ds,
        "real_rate": {d: macro["real_rate"][d] for d in ds if d in macro["real_rate"]},
        "vix": {d: macro["vix"][d] for d in ds if d in macro["vix"]},
        "credit_spread": {d: macro["credit_spread"][d] for d in ds if d in macro["credit_spread"]},
    }


def main():
    gc = build_panel("GC")
    print("=" * 74)
    print(f"GOLD HAVEN | GC {len(gc['dates'])}일 | 고정 파라미터")
    print(f"real_rate_lookback={DEFAULTS['real_rate_lookback']}d "
          f"risk_off_boost={DEFAULTS['risk_off_boost']} rebal={REBAL}d cost={COST_BASE_BPS}bps")
    print("=" * 74)

    macro = build_macro_panel(gc["dates"])
    panels = {"GC": gc}
    params = {**DEFAULTS, "macro": macro}

    strat = run_portfolio(panels, gold_haven_weights, params, COST_BASE_BPS, REBAL)
    sm = strat["metrics"]
    bh = run_portfolio(panels, buyhold_weights, params, COST_BASE_BPS, REBAL)["metrics"]
    stress = run_portfolio(panels, gold_haven_weights, params, COST_STRESS_BPS, REBAL)["metrics"]

    rand_sharpes = []
    for k in range(N_RUNS):
        rng = _random.Random(SEED + k)
        m = run_portfolio(panels, random_weights, params, COST_BASE_BPS, REBAL, rng=rng)["metrics"]
        if m["sharpe"] is not None:
            rand_sharpes.append(m["sharpe"])
    pv = empirical_p_value(sm["sharpe"] or -99, rand_sharpes)

    all_dates = gc["dates"]
    mid = all_dates[len(all_dates) // 2]
    gc_first, gc_second = _filter(gc, all_dates[0], mid), _filter(gc, mid, all_dates[-1] + "~")
    macro_first, macro_second = _filter_macro(macro, all_dates[0], mid), _filter_macro(macro, mid, all_dates[-1] + "~")
    fh = run_portfolio({"GC": gc_first}, gold_haven_weights,
                        {**DEFAULTS, "macro": macro_first}, COST_BASE_BPS, REBAL)["metrics"]
    sh = run_portfolio({"GC": gc_second}, gold_haven_weights,
                        {**DEFAULTS, "macro": macro_second}, COST_BASE_BPS, REBAL)["metrics"]

    print(f"\nGOLD HAVEN: ann_ret={sm['ann_return']} vol={sm['ann_vol']} SHARPE={sm['sharpe']} "
          f"maxDD={sm['max_drawdown']} days={sm['days']}")
    print(f"buyhold   : ann_ret={bh['ann_return']} SHARPE={bh['sharpe']}")
    print(f"stress({COST_STRESS_BPS}bps): SHARPE={stress['sharpe']}")
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

    log_experiment({"hypothesis_id": "gold_haven", "tf": "1d", "rebalance": "daily",
                    "status": "candidate" if passed else "rejected",
                    "sharpe": sm["sharpe"], "ann_return": sm["ann_return"], "max_drawdown": sm["max_drawdown"],
                    "buyhold_sharpe": bh["sharpe"], "stress_sharpe": stress["sharpe"],
                    "random_percentile": pv["percentile"], "p": pv["p_value"],
                    "wf_first_sharpe": fh["sharpe"], "wf_second_sharpe": sh["sharpe"],
                    "n_markets": 1, "verdict": verdict, "note": "fixed params, no tuning, long/flat only"})


if __name__ == "__main__":
    main()
