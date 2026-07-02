"""수동 가설 5종 일괄 검증 (agentic-roadmap Phase 2).

ORB REJECT 이후 엣지 공간 탐색. 고정 파라미터·동일 하네스. 튜닝 금지.
질문: 하나라도 pooled가 비용 후 random 분포를 이기는가? 못 이기면 폐기.

실행: PYTHONPATH=. python3 research/run_all_hypotheses.py
"""
from __future__ import annotations

from research.data.pull_intraday import LIQUID
from research.hypotheses.runner import run_universe, print_result
from research.hypotheses import strategies as S


def main():
    print("=" * 74)
    print("MANUAL HYPOTHESIS SWEEP (fixed params, no tuning) — 엣지 있나 1차 판정")
    print("=" * 74)
    results = []

    results.append(run_universe(
        "vwap_mean_reversion", "VWAP 하방 이탈 + 과매도 → 평균회귀 롱",
        S.vwap_mean_reversion))
    results.append(run_universe(
        "orb_failed_reversal", "OR low 실패돌파(bear trap) → 반전 롱",
        S.orb_failed_reversal))
    results.append(run_universe(
        "gap_continuation", "갭업 + 시가·VWAP 위 유지 → 지속 롱",
        S.gap_continuation))
    results.append(run_universe(
        "atr_compression", "ATR 압축(스퀴즈) 후 N봉 고점 돌파 → 롱",
        S.atr_compression))
    results.append(run_universe(
        "sector_relative_momentum", "종목>섹터ETF>SPY 상대강도 → 롱",
        S.sector_relative_momentum, aux_fn=S.sector_aux, universe=LIQUID))

    for r in results:
        print_result(r)

    print("\n" + "=" * 74)
    print("SUMMARY")
    print("=" * 74)
    for r in results:
        p = r["pooled"]
        print(f"{r['name']:26} pooled_pnl={p['total_pnl']:>12} pct={p['percentile_vs_random']:>5} "
              f"95x={r['exceeders_95pct']['count']}/{r['n_symbols']} BH={r['bh_fdr_survivors']} | {r['verdict']}")


if __name__ == "__main__":
    main()
