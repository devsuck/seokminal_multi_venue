"""사전등록 실험 — H2 cross-sectional funding의 저빈도(weekly) 버전.

PRE-REGISTERED (실행 전 고정):
  변경: rebalance frequency만 daily→weekly(rebalance_days=7).
  동일: trail=3, basket=20%, min_prior=30, universe, long/short count, funding cashflow.
  PRIMARY: weekly + taker cost. 통과기준: net+ · random 95pct 초과 · p<0.05 · WF 양쪽 양수.
  SENSITIVITY: maker cost — maker에서만 통과 시 alpha 아니라 execution feasibility 후보.
  실패 시 HL funding 트랙 폐기. 추가 튜닝 금지.

실행: PYTHONPATH=. python3 research/run_funding_weekly.py
"""
from __future__ import annotations

import glob
import os

from research.backtest.funding_backtester import aggregate_positions
from research.validation.baselines import empirical_p_value
from research.validation.cost_model import hl_effective_cost_bps
from research.hypotheses.funding_strategies import (
    build_daily_panel, cross_sectional_funding, random_cross_sectional,
)
from research.agents.experiment_registry import log_experiment

N_RUNS = 500
SEED = 42
TAKER = hl_effective_cost_bps("major", taker=True)   # 6.0 bps/side
MAKER = hl_effective_cost_bps("major", taker=False)  # 3.0 bps/side
WEEKLY = {"rebalance_days": 7}


def _panels():
    coins = sorted(os.path.basename(f).replace(".parquet", "") for f in glob.glob("data/funding/*.parquet"))
    p = {}
    for c in coins:
        pn = build_daily_panel(c)
        if pn["dates"]:
            p[c] = pn
    return p


def _filter(panels, lo, hi):
    """날짜 [lo,hi) 범위로 패널 제한(walk-forward용)."""
    out = {}
    for c, pn in panels.items():
        dates = [d for d in pn["dates"] if lo <= d < hi]
        if len(dates) < 30:
            continue
        out[c] = {"coin": c, "dates": dates,
                  "close": {d: pn["close"][d] for d in dates},
                  "daily_funding": {d: pn["daily_funding"][d] for d in dates}}
    return out


def _judge(panels, cost, label):
    params = {**WEEKLY, "cost_bps": cost}
    pos = cross_sectional_funding(panels, params)
    agg = aggregate_positions(pos)
    rnd = random_cross_sectional(panels, params, N_RUNS, SEED)
    pv = empirical_p_value(agg["net_pnl"], rnd)
    print(f"\n[{label}] cost={cost}bps/side")
    print(f"  price={agg['price_pnl']} funding={agg['funding_pnl']} cost={agg['trading_cost']} "
          f"net={agg['net_pnl']} trades={agg['num_positions']} win={agg['win_rate']}")
    print(f"  vs random: pct={pv['percentile']} p={pv['p_value']} (rand_med={pv['random_median']})")
    return agg, pv


def main():
    panels = _panels()
    print("=" * 74)
    print(f"PRE-REGISTERED: weekly cross-sectional funding | {len(panels)} coins | "
          f"변경=frequency only(daily→weekly)")
    print("=" * 74)

    # PRIMARY: weekly + taker
    agg, pv = _judge(panels, TAKER, "PRIMARY weekly+taker")

    # walk-forward 2분할 (primary 조건)
    all_dates = sorted(set().union(*[set(pn["dates"]) for pn in panels.values()]))
    mid = all_dates[len(all_dates) // 2]
    fh = aggregate_positions(cross_sectional_funding(_filter(panels, all_dates[0], mid), {**WEEKLY, "cost_bps": TAKER}))
    sh = aggregate_positions(cross_sectional_funding(_filter(panels, mid, all_dates[-1] + "~"), {**WEEKLY, "cost_bps": TAKER}))
    print(f"\n  WF 전반 net={fh['net_pnl']} / 후반 net={sh['net_pnl']}")

    # SENSITIVITY: weekly + maker
    m_agg, m_pv = _judge(panels, MAKER, "SENSITIVITY weekly+maker")

    # 판정
    passed = (agg["net_pnl"] > 0 and (pv["percentile"] or 0) >= 95
              and (pv["p_value"] or 1) < 0.05 and fh["net_pnl"] > 0 and sh["net_pnl"] > 0)
    if passed:
        verdict = "EDGE 후보 (primary weekly+taker 통과)"
    elif m_agg["net_pnl"] > 0 and (m_pv["percentile"] or 0) >= 95:
        verdict = "EXECUTION FEASIBILITY 후보 (maker에서만 통과, alpha 아님)"
    else:
        verdict = "REJECT — HL funding 트랙 폐기"

    print("\n" + "=" * 74 + f"\nVERDICT: {verdict}\n" + "=" * 74)

    log_experiment({"hypothesis_id": "cross_sectional_funding_weekly", "tf": "1d/weekly",
                    "status": "candidate" if passed else "rejected",
                    "price_pnl": agg["price_pnl"], "funding_pnl": agg["funding_pnl"],
                    "trading_cost": agg["trading_cost"], "net_pnl": agg["net_pnl"],
                    "percentile_taker": pv["percentile"], "p_taker": pv["p_value"],
                    "wf_first": fh["net_pnl"], "wf_second": sh["net_pnl"],
                    "net_maker": m_agg["net_pnl"], "percentile_maker": m_pv["percentile"],
                    "verdict": verdict, "note": "pre-registered, frequency-only change, no tuning"})


if __name__ == "__main__":
    main()
