"""Polymarket 샤프월렛 컨버전스 가설 검증 러너 — 통계적 유의미성 스크리닝, 실집행 없음.

`research/run_polymarket_sharp_wallet_collect.py`가 쌓은 체결 원장
(research/data/polymarket_sharp_wallet/)을 읽어 컨버전스 버킷(1/2/3) x
다중호라이즌(30s/120s/300s) forward return을 계산하고,
`research/run_polymarket_whale_validate.py`와 동일하게 랜덤 베이스라인(방향
무작위 셔플) 대비 empirical p-value를 구한다. 최대 9개 p-value를 신규 독립
BH-FDR 풀로 correction한다.

⚠️ 스크리닝 스크립트. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님.
walk-forward는 생략(신규 라이브 수집 직후라 표본기간 미달 — BH-FDR 통과 시
전체 파이프라인 승격 검토).
"""
from __future__ import annotations

import glob
import random as _random
import re

import pandas as pd

from research.hypotheses.polymarket_sharp_wallet import (
    build_convergence_count,
    build_labels_multi_horizon,
    build_price_series,
    load_sharp_wallet_trades,
)
from research.validation.baselines import empirical_p_value
from research.validation.cost_model import polymarket_effective_cost_bps
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/polymarket_sharp_wallet"
CONVERGENCE_BUCKETS = [1, 2, 3]
TRADE_SIZE = 1.0
N_RUNS = 500
SEED = 42
COST_BPS = polymarket_effective_cost_bps()
MIN_EVENTS = 10


def _available_dates() -> list[str]:
    dates = set()
    for path in glob.glob(f"{DATA_DIR}/*.jsonl"):
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.jsonl$", path)
        if m:
            dates.add(m.group(1))
    return sorted(dates)


def run_bucket(bucket: int, labels: pd.DataFrame) -> dict:
    bucket_labels = labels[labels["convergence_bucket"] == bucket]
    if bucket_labels.empty:
        return {"bucket": bucket, "blocked": True, "reason": "라벨 없음"}
    if len(bucket_labels) < MIN_EVENTS:
        return {"bucket": bucket, "blocked": True,
                "reason": f"라벨 {len(bucket_labels)}건뿐 — 최소 표본 미달"}

    rng = _random.Random(SEED)
    horizons: dict[str, dict] = {}
    for h in sorted(bucket_labels["horizon_s"].unique()):
        sub = bucket_labels[bucket_labels["horizon_s"] == h]
        precomputed = []
        for _, row in sub.iterrows():
            entry_px, exit_px = row["entry_price"], row["exit_price"]
            cost = (abs(entry_px) + abs(exit_px)) * TRADE_SIZE * COST_BPS / 10_000.0
            precomputed.append((row["direction"], entry_px, exit_px, cost))

        actual_pnls = [d * (ex - en) * TRADE_SIZE - c for d, en, ex, c in precomputed]
        strat = trade_metrics([{"pnl": pnl} for pnl in actual_pnls])

        random_totals = []
        for _ in range(N_RUNS):
            total = 0.0
            for _d, en, ex, c in precomputed:
                rsign = rng.choice((1.0, -1.0))
                total += rsign * (ex - en) * TRADE_SIZE - c
            random_totals.append(round(total, 6))
        pval = empirical_p_value(strat["total_pnl"], random_totals)
        horizons[f"{int(h)}s"] = {"strategy": strat, "random": pval, "n_events": len(sub)}

    return {"bucket": bucket, "blocked": False, "horizons": horizons}


def main() -> None:
    dates = _available_dates()
    trades = load_sharp_wallet_trades(dates) if dates else pd.DataFrame(columns=[
        "ts", "condition_id", "side", "price", "size", "proxy_wallet",
        "notional_usd", "is_sharp_wallet", "wallet_rank", "wallet_pnl",
    ])

    anchors = build_convergence_count(trades)
    if anchors.empty:
        labels = pd.DataFrame(columns=[
            "ts", "condition_id", "horizon_s", "entry_price", "exit_price",
            "direction", "forward_return", "convergence_bucket",
        ])
    else:
        price_by_condition = {
            cid: build_price_series(trades, cid) for cid in anchors["condition_id"].unique()
        }
        labels = build_labels_multi_horizon(anchors, price_by_condition)

    results = []
    pvals: list[float] = []
    pval_keys: list[str] = []

    for bucket in CONVERGENCE_BUCKETS:
        r = run_bucket(bucket, labels)
        results.append(r)
        if not r["blocked"]:
            for h_key, h_res in r["horizons"].items():
                pvals.append(h_res["random"]["p_value"])
                pval_keys.append(f"bucket{bucket}:{h_key}")

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1,
    }
    bh["keys"] = pval_keys

    print(f"\n=== cost_bps(polymarket) = {COST_BPS} ===\n")
    for r in results:
        if r["blocked"]:
            print(f"bucket{r['bucket']} -> BLOCKED ({r['reason']})")
            continue
        for h_key, h_res in r["horizons"].items():
            s, p = h_res["strategy"], h_res["random"]
            print(f"bucket{r['bucket']}:{h_key} n_events={h_res['n_events']} "
                  f"total_pnl={s['total_pnl']} p_value={p['p_value']} percentile={p['percentile']}")

    print("\n=== BH-FDR (신규 Polymarket sharp-wallet 풀, alpha=0.1) ===")
    print(f"survivors: {[k for k, s in zip(bh['keys'], bh['survivors']) if s]}")
    print(f"n_survivors: {bh['n_survivors']} / {len(pvals)}")


if __name__ == "__main__":
    main()
