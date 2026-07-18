"""BTC.HL 오더플로우 프리미티브 k=2,3-way AND 조합 스윕(C(8,2)+C(8,3)=84개).
255개 전체 스윕(run_orderflow_full_sweep_btc.py) 대비 검정 개수를 줄여 BH-FDR
문턱을 낮춘 버전 — 자체 BH-FDR 풀(스크리닝 전용, 다른 배치와 안 섞음).

⚠️ DORMANT 확인용 스크립트. 실집행 근거 아님.
"""
from __future__ import annotations

import glob

from research.strategies.orderflow_signal_matrix import run_matrix_k
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/hl_orderflow_tick"
SYMBOL = "BTC"
N_RUNS = 500
SEED = 42


def main() -> None:
    paths = sorted(glob.glob(f"{DATA_DIR}/{SYMBOL}_*.jsonl"))
    if not paths:
        print(f"{SYMBOL}: 데이터 없음")
        return

    all_results: list[dict] = []
    for k in (2, 3):
        r = run_matrix_k(f"{SYMBOL}.HL", paths, k, n_runs=N_RUNS, seed=SEED)
        if r.get("blocked"):
            print(f"k={k}: BLOCKED ({r['reason']})")
            continue
        print(f"k={k}: n_bars={r['n_bars']} n_ticks={r['n_ticks']} combos={len(r['results'])}")
        all_results.extend(r["results"])

    valid = [r for r in all_results if r["strategy"]["num_trades"] > 0 and r["random"]["p_value"] is not None]

    print(f"\n=== 조합 스윕 전체({len(all_results)}개, 유효표본 {len(valid)}개) — 수익률 순 ===\n")
    for r in sorted(valid, key=lambda x: x["strategy"]["total_pnl"], reverse=True):
        s, rnd = r["strategy"], r["random"]
        print(f"{r['combo']:30s} trades={s['num_trades']:5d} "
              f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:9.2f} "
              f"expectancy={s['expectancy']:.4f} p={rnd['p_value']:.4f} "
              f"pctile={rnd['percentile']:.1f} underpowered={s['underpowered']} "
              f"eligible={r['eligible_count']}")

    pvals = [r["random"]["p_value"] for r in valid]
    keys = [r["combo"] for r in valid]
    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {"survivors": [], "n_survivors": 0}

    print(f"\n=== BH-FDR (alpha=0.1, 이 스윕 전용 풀, n={len(pvals)}) ===")
    survivors = [k for k, s in zip(keys, bh["survivors"]) if s]
    print(f"n_survivors: {bh['n_survivors']}")
    for k in survivors:
        r = next(x for x in valid if x["combo"] == k)
        print(f"  {k}: total_pnl={r['strategy']['total_pnl']:.2f} win_rate={r['strategy']['win_rate']:.3f} "
              f"p={r['random']['p_value']:.4f} verdict="
              f"{'EDGE CANDIDATE' if r['strategy']['total_pnl'] > 0 else 'SIGNAL-BUT-SUBCOST'}")

    blocked = [r for r in all_results if r["strategy"]["num_trades"] == 0]
    if blocked:
        print(f"\n(참고: 트레이드 0건이라 통계검정 제외된 조합 {len(blocked)}개 — 거의 항상 HOLD)")


if __name__ == "__main__":
    main()
