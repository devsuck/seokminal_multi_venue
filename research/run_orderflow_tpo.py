"""TPO Value Area 이탈 페이드 가설(orderflow_tpo.py) BTC/ETH 백테스트. 자체 BH-FDR 풀
(2-way/3-way/4-way+다수결/메이커재검증과 안 섞음).

⚠️ DORMANT 확인용 스크립트. 실집행 근거 아님.
"""
from __future__ import annotations

import glob
import json

from orderflow.aggregator import OrderflowAggregator
from orderflow.models import TradeEvent
from research.strategies.orderflow_tpo import run_hypothesis
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/hl_orderflow_tick"
N_RUNS = 500
SEED = 42


def load_raw_ticks(paths: list[str]) -> list[dict]:
    ticks = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def main() -> None:
    results = []
    for symbol in ("BTC", "ETH"):
        paths = sorted(glob.glob(f"{DATA_DIR}/{symbol}_*.jsonl"))
        if not paths:
            print(f"{symbol}: 데이터 없음, 스킵")
            continue
        ticks = load_raw_ticks(paths)
        agg = OrderflowAggregator()
        deltas = [
            agg.on_trade(TradeEvent(symbol=f"{symbol}.HL", ts=t["ts"], price=t["price"],
                                     size=t["size"], side=t["side"]))
            for t in ticks
        ]
        r = run_hypothesis(f"{symbol}.HL", deltas, n_runs=N_RUNS, seed=SEED, write_report=True)
        results.append(r)
        if r.get("blocked"):
            print(f"{symbol}: BLOCKED ({r['reason']})")
            continue
        s, rnd, wf = r["strategy"], r["random"], r["walk_forward"]
        print(
            f"{symbol}: n_bars={r['n_bars']} eligible={r['eligible_count']} "
            f"trades={s['num_trades']} win_rate={s['win_rate']:.3f} "
            f"total_pnl={s['total_pnl']:.2f} expectancy={s['expectancy']:.4f} "
            f"p={rnd['p_value']:.4f} pctile={rnd['percentile']:.1f} "
            f"underpowered={s['underpowered']} consistency={wf['consistency']}"
        )

    valid = [r for r in results if not r.get("blocked") and r["strategy"]["num_trades"] > 0]
    if valid:
        pvals = [r["random"]["p_value"] for r in valid]
        keys = [r["symbol"] for r in valid]
        bh = benjamini_hochberg(pvals, alpha=0.1)
        print(f"\n=== BH-FDR (alpha=0.1, TPO 전용 풀, n={len(pvals)}) ===")
        print(f"n_survivors: {bh['n_survivors']}")
        for k, s in zip(keys, bh["survivors"]):
            if s:
                r = next(x for x in valid if x["symbol"] == k)
                verdict = "EDGE CANDIDATE" if r["strategy"]["total_pnl"] > 0 else "SIGNAL-BUT-SUBCOST"
                print(f"  {k}: total_pnl={r['strategy']['total_pnl']:.2f} verdict={verdict}")


if __name__ == "__main__":
    main()
