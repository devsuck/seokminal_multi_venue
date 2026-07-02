"""TSMOM 로버스트니스 3종 (paper 전 관문, 최적화 아님).

1. N=1000 random distribution → p<0.05 유지?
2. lookback 민감도 3/6/12개월 → Sharpe 여러 구간 양수? (신호군 견고성)
3. 연도별/sleeve 집중도 → 한 해/한 sleeve에만 쏠리지 않나 (concentration 진단)

통과: N=1000 p<0.05 + lookback 다구간 양수 + WF 양쪽 양수 + 집중 아님.
"""
from __future__ import annotations

import random as _random

from research.backtest.portfolio_backtester import run_portfolio
from research.validation.baselines import empirical_p_value
from research.hypotheses.tsmom import build_panel, tsmom_weights, random_weights, DEFAULTS
from research.data.futures_loader import BASKET, ASSET_CLASS

COST_BPS = 5.0  # 보수적(중간)
REBAL = 21
SEED = 42


def panels():
    out = {}
    for s, _ in BASKET:
        p = build_panel(s)
        if len(p["dates"]) > DEFAULTS["lookback"] + DEFAULTS["vol_window"] + 30:
            out[s] = p
    return out


def random_dist(pn, params, n, cost):
    rs = []
    for k in range(n):
        m = run_portfolio(pn, random_weights, params, cost, REBAL, rng=_random.Random(SEED + k))["metrics"]
        if m["sharpe"] is not None:
            rs.append(m["sharpe"])
    return rs


def main():
    pn = panels()
    print(f"TSMOM ROBUSTNESS | {len(pn)} markets | cost={COST_BPS}bps\n")

    # ── 1. N=1000 random ─────────────────────────────────────────────
    strat = run_portfolio(pn, tsmom_weights, {}, COST_BPS, REBAL)
    sm = strat["metrics"]
    rs = random_dist(pn, {}, 1000, COST_BPS)
    pv = empirical_p_value(sm["sharpe"] or -9, rs)
    print(f"[1] N=1000 random: strat sharpe={sm['sharpe']} pct={pv['percentile']} p={pv['p_value']} "
          f"(rand med={pv['random_median']})")
    pass1 = (pv["p_value"] or 1) < 0.05

    # ── 2. lookback 민감도 ────────────────────────────────────────────
    print("\n[2] lookback 민감도 (3/6/12개월):")
    lb_sharpes = []
    for lb in [63, 126, 252]:
        m = run_portfolio(pn, tsmom_weights, {"lookback": lb}, COST_BPS, REBAL)["metrics"]
        rlb = random_dist(pn, {"lookback": lb}, 200, COST_BPS)
        p = empirical_p_value(m["sharpe"] or -9, rlb)
        lb_sharpes.append(m["sharpe"] or -9)
        print(f"   lookback={lb:3}d  sharpe={m['sharpe']}  ann_ret={m['ann_return']}  vs_random p={p['p_value']}")
    pass2 = all(s > 0 for s in lb_sharpes)

    # ── 3. 연도별 + sleeve 집중도 ─────────────────────────────────────
    print("\n[3] 연도별 성과 (집중도):")
    daily, dates = strat["daily_returns"], strat["dates"]
    by_year = {}
    for r, d in zip(daily, dates):
        by_year.setdefault(d[:4], []).append(r)
    ann = {}
    for y, rs2 in sorted(by_year.items()):
        tot = 1.0
        for r in rs2:
            tot *= (1 + r)
        ann[y] = tot - 1
        print(f"   {y}: {tot-1:+.4f} ({len(rs2)}d)")
    pos_years = sum(1 for v in ann.values() if v > 0)
    best_year = max(ann, key=ann.get)
    total_ret = sm["total_return"]
    ex_best = total_ret - ann[best_year]
    print(f"   양수 연도: {pos_years}/{len(ann)} | 최고 {best_year}({ann[best_year]:+.4f}) 제외 시 총수익 {ex_best:+.4f}")

    print("\n[sleeve 집중도]:")
    classes = {}
    for a in pn:
        classes.setdefault(ASSET_CLASS.get(a, "?"), []).append(a)
    sleeve_sh = {}
    for cls, syms in sorted(classes.items()):
        m = run_portfolio({a: pn[a] for a in syms}, tsmom_weights, {}, COST_BPS, REBAL)["metrics"]
        sleeve_sh[cls] = m["sharpe"]
        print(f"   {cls:10} sharpe={m['sharpe']}")
    pos_sleeves = sum(1 for v in sleeve_sh.values() if (v or 0) > 0)
    pass3 = (pos_years >= len(ann) * 0.6 and ex_best > 0 and pos_sleeves >= len(sleeve_sh) * 0.5)

    # WF
    all_dates = sorted(set().union(*[set(p["dates"]) for p in pn.values()]))
    mid = all_dates[len(all_dates) // 2]
    def _flt(lo, hi):
        o = {}
        for a, p in pn.items():
            ds = [d for d in p["dates"] if lo <= d < hi]
            if len(ds) > DEFAULTS["lookback"] + DEFAULTS["vol_window"] + 10:
                o[a] = {"symbol": a, "dates": ds, "close": {d: p["close"][d] for d in ds}}
        return o
    fh = run_portfolio(_flt(all_dates[0], mid), tsmom_weights, {}, COST_BPS, REBAL)["metrics"]
    sh = run_portfolio(_flt(mid, all_dates[-1] + "~"), tsmom_weights, {}, COST_BPS, REBAL)["metrics"]
    pass_wf = (fh["sharpe"] or -9) > 0 and (sh["sharpe"] or -9) > 0

    print("\n" + "=" * 60)
    print(f"[1] N=1000 p<0.05:        {'PASS' if pass1 else 'FAIL'} (p={pv['p_value']})")
    print(f"[2] lookback 다구간 양수:  {'PASS' if pass2 else 'FAIL'} ({lb_sharpes})")
    print(f"[3] 집중 아님:            {'PASS' if pass3 else 'FAIL'} (연도 {pos_years}/{len(ann)}, sleeve {pos_sleeves}/{len(sleeve_sh)})")
    print(f"[WF] 양쪽 양수:           {'PASS' if pass_wf else 'FAIL'} ({fh['sharpe']}/{sh['sharpe']})")
    allpass = pass1 and pass2 and pass3 and pass_wf
    print(f"\n판정: {'✅ PAPER FORWARD-TEST 후보 등록' if allpass else '❌ watchlist/reject'}")


if __name__ == "__main__":
    main()
