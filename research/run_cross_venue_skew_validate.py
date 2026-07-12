"""크로스벤뉴 오더북 스큐 가설 검증 러너 — 통계적 유의미성 스크리닝, 실집행 없음.

`research/run_cross_venue_skew_collect.py`가 쌓은 벤뉴별 원장(research/data/cross_venue_skew/)을
읽어 임밸런스 괴리 스파이크 -> 다중호라이즌(5s/15s/60s) forward return을 계산하고,
`research/run_orderflow_futures_on_btc.py`의 `run_stop_run` 패턴과 동일하게(이벤트
타이밍은 고정, 방향만 무작위로 섞는) 랜덤 베이스라인 대비 empirical p-value를 구한다.
코인2 x 호라이즌3 = 6개 p-value를 기존 오더플로우 배치들과 분리된 신규 BH-FDR 풀로
correction한다.

⚠️ 스크리닝 스크립트. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님. walk-forward는
생략(`run_orderflow_futures_on_btc.py`와 동일 사유 — 신규 라이브 수집 직후라 표본 기간이
walk-forward 분할에 미달, BH-FDR 통과 시 전체 파이프라인으로 승격 검토).
"""
from __future__ import annotations

import glob
import random as _random
import re

from research.hypotheses.cross_venue_skew import (
    align_venues,
    build_imbalance,
    build_labels_multi_horizon,
    build_price_series,
    build_skew_divergence,
    build_spike_signal,
    load_venue_snapshots,
)
from research.validation.baselines import empirical_p_value
from research.validation.cost_model import hl_effective_cost_bps
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/cross_venue_skew"
COINS = ["BTC", "ETH"]
VENUES = ["hl", "binance", "okx"]
TRADE_SIZE = 1.0
N_RUNS = 500
SEED = 42
COST_BPS = hl_effective_cost_bps("major", taker=True)
MIN_EVENTS = 10


def _available_dates(coin: str) -> list[str]:
    dates = set()
    for venue in VENUES:
        for path in glob.glob(f"{DATA_DIR}/{venue}_{coin}_*.jsonl"):
            m = re.search(r"(\d{4}-\d{2}-\d{2})\.jsonl$", path)
            if m:
                dates.add(m.group(1))
    return sorted(dates)


def run_coin(coin: str) -> dict:
    dates = _available_dates(coin)
    if not dates:
        return {"coin": coin, "blocked": True, "reason": "데이터 없음"}

    raw_by_venue = {venue: load_venue_snapshots(venue, coin, dates) for venue in VENUES}
    raw_by_venue = {v: df for v, df in raw_by_venue.items() if not df.empty}
    if len(raw_by_venue) < 2:
        return {"coin": coin, "blocked": True, "reason": f"유효 벤뉴 {len(raw_by_venue)}개뿐 — 최소 2개 필요"}

    imbalance_by_venue = {v: build_imbalance(df) for v, df in raw_by_venue.items()}
    aligned = align_venues(imbalance_by_venue)
    divergence = build_skew_divergence(aligned)
    spikes = build_spike_signal(divergence)
    price = build_price_series(raw_by_venue)
    labels = build_labels_multi_horizon(price, spikes)

    if len(labels) < MIN_EVENTS:
        return {"coin": coin, "blocked": True, "reason": f"스파이크 이벤트 {len(labels)}건뿐 — 최소 표본 미달"}

    rng = _random.Random(SEED)
    horizons: dict[str, dict] = {}
    for h in sorted(labels["horizon_s"].unique()):
        sub = labels[labels["horizon_s"] == h]
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

    return {"coin": coin, "blocked": False, "horizons": horizons}


def main() -> None:
    results = []
    pvals: list[float] = []
    pval_keys: list[str] = []

    for coin in COINS:
        r = run_coin(coin)
        results.append(r)
        if not r["blocked"]:
            for h_key, h_res in r["horizons"].items():
                pvals.append(h_res["random"]["p_value"])
                pval_keys.append(f"{coin}:{h_key}")

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1,
    }
    bh["keys"] = pval_keys

    print(f"\n=== cost_bps(HL major taker) = {COST_BPS} ===\n")
    for r in results:
        if r["blocked"]:
            print(f"{r['coin']} -> BLOCKED ({r['reason']})")
            continue
        for h_key, h_res in r["horizons"].items():
            s, p = h_res["strategy"], h_res["random"]
            print(f"{r['coin']}:{h_key} n_events={h_res['n_events']} "
                  f"total_pnl={s['total_pnl']} p_value={p['p_value']} percentile={p['percentile']}")

    print("\n=== BH-FDR (신규 크로스벤뉴 스큐 풀, alpha=0.1) ===")
    print(f"survivors: {[k for k, s in zip(bh['keys'], bh['survivors']) if s]}")
    print(f"n_survivors: {bh['n_survivors']} / {len(pvals)}")


if __name__ == "__main__":
    main()
