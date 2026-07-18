"""4-way 전원합의 AND(C(8,4)=70/심볼) + 다수결(3/4/5/6-of-8, 4/심볼) 스윕. 2-way/3-way
AND 스윕(둘 다 0 생존) 뒤 유저 요청("3,4개 조합 다 해봐")에 대한 후속. AND는 k가
커질수록 교집합이 기하급수로 줄어 표본이 죽는 경향이 3-way에서부터 뚜렷했음 —
그래서 겹침 요구가 낮은 다수결도 같이 돌려 "AND가 너무 빡빡해서 못 본 신호"인지
"애초에 신호가 없는 것"인지 구분한다. 자체 BH-FDR 풀(다른 배치와 안 섞음).

⚠️ DORMANT 확인용 스크립트. 실집행 근거 아님.
"""
from __future__ import annotations

import glob

from research.strategies.orderflow_signal_matrix import run_majority_matrix, run_matrix_k
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

        r4 = run_matrix_k(f"{symbol}.HL", paths, k=4, n_runs=N_RUNS, seed=SEED)
        if r4.get("blocked"):
            print(f"{symbol} k=4: BLOCKED ({r4['reason']})")
        else:
            print(f"{symbol} k=4: n_bars={r4['n_bars']} combos={len(r4['results'])}")
            all_results.extend(r4["results"])

        rm = run_majority_matrix(f"{symbol}.HL", paths, thresholds=(3, 4, 5, 6), n_runs=N_RUNS, seed=SEED)
        if rm.get("blocked"):
            print(f"{symbol} majority: BLOCKED ({rm['reason']})")
        else:
            print(f"{symbol} majority: n_bars={rm['n_bars']} combos={len(rm['results'])}")
            all_results.extend(rm["results"])

    valid = [r for r in all_results if r["strategy"]["num_trades"] > 0 and r["random"]["p_value"] is not None]

    print(f"\n=== 4-way AND + 다수결 스윕 전체({len(all_results)}개, 유효표본 {len(valid)}개) — 수익률 순 ===\n")
    for r in sorted(valid, key=lambda x: x["strategy"]["total_pnl"], reverse=True):
        s, rnd = r["strategy"], r["random"]
        print(f"{r['symbol']}:{r['combo']:50s} trades={s['num_trades']:5d} "
              f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:9.2f} "
              f"expectancy={s['expectancy']:.4f} p={rnd['p_value']:.4f} "
              f"pctile={rnd['percentile']:.1f} underpowered={s['underpowered']} "
              f"eligible={r['eligible_count']}")

    print(f"\n=== 승률 순(트레이드≥30만) ===\n")
    win_ranked = [r for r in valid if r["strategy"]["num_trades"] >= 30]
    for r in sorted(win_ranked, key=lambda x: x["strategy"]["win_rate"], reverse=True)[:20]:
        s, rnd = r["strategy"], r["random"]
        print(f"{r['symbol']}:{r['combo']:50s} trades={s['num_trades']:5d} "
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
