"""8개 오더플로우 프리미티브 조합 스윕(footprint/absorption/cvd/large_trade/tape_vwap/
vwap_window/trend_15m/key_level_15m) — 페어와이즈 AND 28개 + killzone게이트 8개 =
심볼당 36개, BTC+ETH 합쳐 72개. 자체 BH-FDR 풀(스크리닝 전용, 다른 배치와 안 섞음).
결과는 수익률(total_pnl)/승률(win_rate) 순 정렬로 출력 — 유저 요청 반영.

⚠️ DORMANT 확인용 스크립트. 72개 동시검정 스크리닝 — 실집행 근거 아님.
"""
from __future__ import annotations

import glob

from research.strategies.orderflow_signal_matrix import run_matrix
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/hl_orderflow_tick"
N_RUNS = 500
SEED = 42


def main() -> None:
    all_results: list[dict] = []

    for symbol in ("BTC", "ETH"):
        paths = sorted(glob.glob(f"{DATA_DIR}/{symbol}_*.jsonl"))
        if not paths:
            print(f"{symbol}: 데이터 없음, 스킵")
            continue
        r = run_matrix(f"{symbol}.HL", paths, n_runs=N_RUNS, seed=SEED)
        if r.get("blocked"):
            print(f"{symbol}: BLOCKED ({r['reason']})")
            continue
        print(f"{symbol}: n_bars={r['n_bars']} n_ticks={r['n_ticks']} combos={len(r['results'])}")
        all_results.extend(r["results"])

    valid = [r for r in all_results if r["strategy"]["num_trades"] > 0 and r["random"]["p_value"] is not None]

    print(f"\n=== 조합 스윕 전체({len(all_results)}개, 유효표본 {len(valid)}개) — 수익률 순 ===\n")
    for r in sorted(valid, key=lambda x: x["strategy"]["total_pnl"], reverse=True):
        s, rnd = r["strategy"], r["random"]
        print(f"{r['symbol']}:{r['combo']:28s} trades={s['num_trades']:5d} "
              f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:9.2f} "
              f"expectancy={s['expectancy']:.4f} p={rnd['p_value']:.4f} "
              f"pctile={rnd['percentile']:.1f} underpowered={s['underpowered']} "
              f"eligible={r['eligible_count']}")

    print(f"\n=== 승률 순(트레이드≥30만) ===\n")
    win_ranked = [r for r in valid if r["strategy"]["num_trades"] >= 30]
    for r in sorted(win_ranked, key=lambda x: x["strategy"]["win_rate"], reverse=True)[:15]:
        s, rnd = r["strategy"], r["random"]
        print(f"{r['symbol']}:{r['combo']:28s} trades={s['num_trades']:5d} "
              f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:9.2f} p={rnd['p_value']:.4f}")

    pvals = [r["random"]["p_value"] for r in valid]
    keys = [f"{r['symbol']}:{r['combo']}" for r in valid]
    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {"survivors": [], "n_survivors": 0}

    print(f"\n=== BH-FDR (alpha=0.1, 이 스윕 전용 풀, n={len(pvals)}) ===")
    survivors = [k for k, s in zip(keys, bh["survivors"]) if s]
    print(f"n_survivors: {bh['n_survivors']}")
    for k in survivors:
        r = next(x for x in valid if f"{x['symbol']}:{x['combo']}" == k)
        print(f"  {k}: total_pnl={r['strategy']['total_pnl']:.2f} win_rate={r['strategy']['win_rate']:.3f} "
              f"p={r['random']['p_value']:.4f} verdict="
              f"{'EDGE CANDIDATE' if r['strategy']['total_pnl'] > 0 else 'SIGNAL-BUT-SUBCOST'}")

    blocked = [r for r in all_results if r["strategy"]["num_trades"] == 0]
    if blocked:
        print(f"\n(참고: 트레이드 0건이라 통계검정 제외된 조합 {len(blocked)}개 — 거의 항상 HOLD)")


if __name__ == "__main__":
    main()
