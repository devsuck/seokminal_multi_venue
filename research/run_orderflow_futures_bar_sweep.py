"""NQ/MNQ/GC 15분봉 바-레벨 오더플로우 프리미티브(vwap_window/trend_15m/key_level_15m)
조합 스윕 — 심볼당 7개(단일3+페어와이즈AND3+3wayAND1), 3심볼 합쳐 21개.
자체 BH-FDR 풀(스크리닝 전용, 다른 배치와 안 섞음).

⚠️ tick 데이터 부재로 footprint/absorption/cvd/large_trade/tape_vwap는 제외됨.
BTC.HL 8-프리미티브 255콤보 스윕과 표본 크기·검정력이 다르다 — 같은 급 비교 금지.
⚠️ DORMANT 확인용 스크립트. 실집행 근거 아님.
"""
from __future__ import annotations

from research.data.intraday_store import load_ohlc_lists
from research.strategies.orderflow_futures_bar_matrix import run_matrix
from research.validation.multiple_testing import benjamini_hochberg

SYMBOLS = ("NQ", "MNQ", "GC")
TF = "15m"
N_RUNS = 500
SEED = 42


def main() -> None:
    all_results: list[dict] = []

    for symbol in SYMBOLS:
        bars = load_ohlc_lists(symbol, TF)
        if not bars["ts"]:
            print(f"{symbol}: 데이터 없음, 스킵")
            continue
        r = run_matrix(symbol, bars, n_runs=N_RUNS, seed=SEED)
        if r.get("blocked"):
            print(f"{symbol}: BLOCKED ({r['reason']})")
            continue
        first_ts, last_ts = bars["ts"][0], bars["ts"][-1]
        print(f"{symbol}: n_bars={r['n_bars']} range=[{first_ts}..{last_ts}] combos={len(r['results'])}")
        all_results.extend(r["results"])

    valid = [r for r in all_results if r["strategy"]["num_trades"] > 0 and r["random"]["p_value"] is not None]

    print(f"\n=== 조합 스윕 전체({len(all_results)}개, 유효표본 {len(valid)}개) — 수익률 순 ===\n")
    for r in sorted(valid, key=lambda x: x["strategy"]["total_pnl"], reverse=True):
        s, rnd = r["strategy"], r["random"]
        print(f"{r['symbol']}:{r['combo']:35s} trades={s['num_trades']:5d} "
              f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:10.2f} "
              f"expectancy={s['expectancy']:.4f} p={rnd['p_value']:.4f} "
              f"pctile={rnd['percentile']:.1f} underpowered={s['underpowered']} "
              f"eligible={r['eligible_count']}")

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
