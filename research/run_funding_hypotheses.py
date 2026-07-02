"""Funding 가설 실판정 (고정 파라미터, 튜닝 금지).

질문: funding 정보가 가격변동 + 비용을 이기고, funding-aware random을 넘는가?
분해: price_pnl / funding_pnl / cost / net (가격손실을 funding이 메우는 구조인지).

실행: PYTHONPATH=. python3 research/run_funding_hypotheses.py
"""
from __future__ import annotations

import glob
import os

from research.data.funding_store import quality_report
from research.backtest.funding_backtester import aggregate_positions
from research.validation.baselines import empirical_p_value
from research.validation.multiple_testing import benjamini_hochberg
from research.hypotheses.funding_strategies import (
    build_daily_panel, funding_extreme_reversal, random_reversal,
    cross_sectional_funding, random_cross_sectional, DEFAULTS_REVERSAL,
)
from research.agents.experiment_registry import log_experiment

N_RUNS = 500
SEED = 42


def _coins() -> list[str]:
    return sorted(os.path.basename(f).replace(".parquet", "") for f in glob.glob("data/funding/*.parquet"))


def _decomp(agg: dict) -> str:
    return (f"price={agg['price_pnl']} funding={agg['funding_pnl']} "
            f"cost={agg['trading_cost']} net={agg['net_pnl']}")


def run_reversal(panels: dict):
    print("\n" + "=" * 74 + "\n### H1 funding extreme reversal (z>±2, 3d hold, 고정)\n" + "=" * 74)
    pooled, rand_matrix, per_coin_p = [], [], []
    hold = DEFAULTS_REVERSAL["hold_days"]
    for c, pn in panels.items():
        if len(pn["dates"]) < 100:
            continue
        pos = funding_extreme_reversal(pn)
        if not pos:
            continue
        pooled.extend(pos)
        agg = aggregate_positions(pos)
        rnd = random_reversal(pn, len(pos), hold, N_RUNS, SEED)
        pv = empirical_p_value(agg["net_pnl"], rnd)
        rand_matrix.append(rnd)
        per_coin_p.append(pv["p_value"])
    agg = aggregate_positions(pooled)
    pooled_random = [sum(col) for col in zip(*rand_matrix)] if rand_matrix else []
    ppv = empirical_p_value(agg["net_pnl"], pooled_random)
    bh = benjamini_hochberg([p for p in per_coin_p if p is not None], alpha=0.1)
    print(f"  POOLED {_decomp(agg)}  trades={agg['num_positions']} win={agg['win_rate']}")
    print(f"  vs random: pct={ppv['percentile']} p={ppv['empirical_p_value'] if 'empirical_p_value' in ppv else ppv['p_value']} (rand_med={ppv['random_median']})")
    print(f"  coins={len(rand_matrix)} BH생존={bh['n_survivors']}")
    return agg, ppv, bh


def run_xsect(panels: dict):
    print("\n" + "=" * 74 + "\n### H2 cross-sectional funding (하위 롱/상위 숏, top/bottom 20%, 1d, 고정)\n" + "=" * 74)
    pos = cross_sectional_funding(panels)
    agg = aggregate_positions(pos)
    rnd = random_cross_sectional(panels, None, N_RUNS, SEED)
    pv = empirical_p_value(agg["net_pnl"], rnd)
    # OOS 2분할(날짜 기준)
    print(f"  POOLED {_decomp(agg)}  trades={agg['num_positions']} win={agg['win_rate']}")
    print(f"  vs random: pct={pv['percentile']} p={pv['p_value']} (rand_med={pv['random_median']})")
    return agg, pv


def verdict(agg, pv, bh=None) -> str:
    net = agg["net_pnl"]; pct = pv.get("percentile") or 0
    fund_key = agg["funding_pnl"]
    if net > 0 and pct >= 95 and (bh is None or bh["n_survivors"] >= 1):
        return "EDGE 후보 — net+ · random 95pct 초과" + (" · BH생존" if bh and bh["n_survivors"] else "")
    if net > 0 and pct >= 80:
        return "WATCHLIST — net+ · random 80~95pct (튜닝 금지, 추가데이터 재확인)"
    if net <= 0:
        return "REJECT — net 음수(비용 후 사망)"
    return "REJECT/약함 — random 80pct 미만"


def main():
    coins = _coins()
    print(f"[QA] {len(coins)} coins funding")
    panels = {}
    for c in coins:
        pn = build_daily_panel(c)
        if pn["dates"]:
            panels[c] = pn
    print(f"[panels] {len(panels)} coins with aligned close+funding")

    r_agg, r_pv, r_bh = run_reversal(panels)
    x_agg, x_pv = run_xsect(panels)

    print("\n" + "=" * 74 + "\nVERDICTS\n" + "=" * 74)
    v1 = verdict(r_agg, r_pv, r_bh)
    v2 = verdict(x_agg, x_pv)
    print(f"H1 reversal:      {v1}")
    print(f"H2 cross-sectional: {v2}")

    for hid, agg, pv, v in [("funding_extreme_reversal", r_agg, r_pv, v1),
                            ("cross_sectional_funding", x_agg, x_pv, v2)]:
        log_experiment({"hypothesis_id": hid, "tf": "1d", "status": "rejected" if "REJECT" in v else "watchlist" if "WATCHLIST" in v else "candidate",
                        "price_pnl": agg["price_pnl"], "funding_pnl": agg["funding_pnl"],
                        "trading_cost": agg["trading_cost"], "net_pnl": agg["net_pnl"],
                        "trade_count": agg["num_positions"], "percentile": pv.get("percentile"),
                        "verdict": v, "note": "HL perp funding, fixed params, no tuning"})


if __name__ == "__main__":
    main()
