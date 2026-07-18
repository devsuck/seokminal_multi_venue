"""체결속도버스트×VWAP밴드 페이드 가설(orderflow_tape_vwap.py) — BTC/ETH(HL) 8일치
틱으로 실행. 신규 조합가설이라 BH-FDR 풀은 이전 배치(footprint/absorption/cvd 등)와
별도로 둔다(design spec: "새 가설은 별도 BH-FDR 풀, 이전 배치와 안 섞음" 원칙 계승).

⚠️ DORMANT 확인용 스크립트. 결과는 통계적 스크리닝일 뿐 실집행 근거 아님.
"""
from __future__ import annotations

import glob

from research.strategies.orderflow_tape_vwap import run_hypothesis
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/hl_orderflow_tick"
N_RUNS = 500
SEED = 42


def main() -> None:
    results: list[dict] = []
    pvals: list[float] = []
    pval_keys: list[str] = []

    for symbol in ("BTC", "ETH"):
        paths = sorted(glob.glob(f"{DATA_DIR}/{symbol}_*.jsonl"))
        if not paths:
            print(f"{symbol}: 데이터 없음, 스킵")
            continue
        r = run_hypothesis(f"{symbol}.HL", paths, n_runs=N_RUNS, seed=SEED)
        results.append(r)
        if not r["blocked"]:
            pvals.append(r["random"]["p_value"])
            pval_keys.append(f"{symbol}.HL:tape_vwap_fade")

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {"survivors": [], "alpha": 0.1}
    bh["keys"] = pval_keys

    print("\n=== orderflow_tape_vwap (체결속도버스트 x VWAP밴드 페이드) ===\n")
    for r in results:
        if r["blocked"]:
            print(f"{r['symbol']} -> BLOCKED ({r['reason']})")
            continue
        s = r["strategy"]
        print(f"{r['symbol']} -> trades={s['num_trades']} win_rate={s['win_rate']:.3f} "
              f"total_pnl={s['total_pnl']:.2f} expectancy={s['expectancy']:.4f} "
              f"p_value={r['random']['p_value']:.4f} percentile={r['random']['percentile']} "
              f"underpowered={s['underpowered']} "
              f"(n_bars={r['n_bars']}, eligible={r['eligible_count']}, n_ticks={r['n_ticks']})")
        print(f"   walk_forward: {r['walk_forward']}")
        print(f"   verdict: {r['report']['verdict']}")

    print("\n=== BH-FDR (alpha=0.1, 이 가설 전용 풀) ===")
    print(f"keys: {bh['keys']}")
    print(f"survivors: {bh['survivors']}")
    print(f"n_survivors: {bh['n_survivors']}")


if __name__ == "__main__":
    main()
