"""Polymarket whale 동시다발 동조 가설 검증 러너 — 통계적 유의미성 스크리닝, 실집행 없음.

`research/run_polymarket_whale_collect.py`가 쌓은 체결 원장을 `run_polymarket_whale_validate.py`와
동일하게 읽되, 스파이크(개별 고래체결) 다음 단계에서 단일 지갑이 아니라
`build_coincidence_signal`(같은 마켓·같은 방향으로 60초 내 서로 다른 지갑 2개 이상
동조)로 신호를 좁힌 뒤 나머지(다중호라이즌 forward return, 랜덤 베이스라인 p-value,
BH-FDR, walk-forward 게이트)는 그대로 재사용한다. `polymarket_whale`(순수 사이즈
z-score, 3연속 no_edge)과 별개 독립 BH-FDR 풀 — 서로 다른 가설이라 correction을
섞지 않는다.

⚠️ 스크리닝 스크립트. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님.
"""
from __future__ import annotations

import random as _random
from pathlib import Path

import pandas as pd

from research import jsonl_dates
from research.hypotheses.polymarket_whale_coincidence import (
    build_coincidence_signal,
    build_labels_multi_horizon,
    build_notional_zscore,
    build_price_series,
    build_spike_signal,
    load_whale_trades,
)
from research.run_polymarket_whale_validate import _walk_forward
from research.validation.baselines import empirical_p_value
from research.validation.cost_model import polymarket_effective_cost_bps
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/polymarket_whale"
FAMILIES = ["news", "sports"]
TRADE_SIZE = 1.0
N_RUNS = 500
SEED = 42
COST_BPS = polymarket_effective_cost_bps()
MIN_EVENTS = 10


def _available_dates() -> list[str]:
    return jsonl_dates.list_dates(Path(DATA_DIR))


def run_family(family: str, df: pd.DataFrame) -> dict:
    fam_df = df[df["family"] == family]
    if fam_df.empty:
        return {"family": family, "blocked": True, "reason": "데이터 없음"}

    df_z = build_notional_zscore(fam_df)
    spikes = build_spike_signal(df_z)
    coincidences = build_coincidence_signal(spikes)
    if coincidences.empty:
        return {"family": family, "blocked": True, "reason": "동조 클러스터 없음"}

    market_outcome_pairs = {
        (cid, oi) for cid, oi in coincidences[["condition_id", "outcome_index"]].itertuples(index=False)
        if oi in (0, 1)
    }
    price_by_condition = {
        key: build_price_series(fam_df, key[0], key[1]) for key in market_outcome_pairs
    }
    labels = build_labels_multi_horizon(price_by_condition, coincidences)

    if len(labels) < MIN_EVENTS:
        return {"family": family, "blocked": True, "reason": f"라벨 {len(labels)}건뿐 — 최소 표본 미달"}

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
        horizons[f"{int(h)}s"] = {"strategy": strat, "random": pval, "n_events": len(sub),
                                   "walk_forward": _walk_forward(precomputed)}

    return {"family": family, "blocked": False, "horizons": horizons}


def _group_to_dict(gname: str, r: dict) -> tuple[dict, list[float], list[str], dict[str, bool]]:
    if r["blocked"]:
        return {"group": gname, "blocked": True, "reason": r.get("reason", "")}, [], [], {}
    horizons, pvals, keys, wf_ok = [], [], [], {}
    for hk, hv in r["horizons"].items():
        horizons.append({"horizon": hk, "n_events": hv["n_events"],
                         "total_pnl": hv["strategy"]["total_pnl"],
                         "p_value": hv["random"]["p_value"], "percentile": hv["random"]["percentile"],
                         "walk_forward": hv["walk_forward"]})
        pvals.append(hv["random"]["p_value"])
        key = f"{gname}:{hk}"
        keys.append(key)
        wf_ok[key] = hv["walk_forward"]["both_positive"]
    return {"group": gname, "blocked": False, "horizons": horizons}, pvals, keys, wf_ok


def compute_report(df: pd.DataFrame, dates: list[str]) -> dict:
    if df.empty:
        return {"hypothesis": "polymarket_whale_coincidence", "cost_bps": COST_BPS, "dates": dates,
                "n_anchors": 0, "groups": [], "pools": [], "verdict": "no_data"}
    groups: list[dict] = []
    pvals: list[float] = []
    keys: list[str] = []
    wf_ok: dict[str, bool] = {}
    n_labels = 0
    for family in FAMILIES:
        g, pv, ks, wf = _group_to_dict(family, run_family(family, df))
        groups.append(g)
        pvals += pv
        keys += ks
        wf_ok |= wf
        if not g["blocked"]:
            n_labels += sum(h["n_events"] for h in g["horizons"])

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1}
    survivors_raw = [k for k, s in zip(keys, bh["survivors"]) if s]
    survivors = [k for k in survivors_raw if wf_ok.get(k)]
    pool = {"name": "whale_coincidence", "alpha": bh["alpha"], "n_tested": len(pvals),
            "n_survivors": len(survivors), "survivors": survivors,
            "survivors_before_walk_forward": survivors_raw, "threshold": bh.get("threshold")}
    return {"hypothesis": "polymarket_whale_coincidence", "cost_bps": COST_BPS, "dates": dates,
            "n_anchors": n_labels, "groups": groups, "pools": [pool],
            "verdict": "candidate" if pool["n_survivors"] > 0 else "no_edge"}


def load_and_report() -> dict:
    dates = _available_dates()
    df = load_whale_trades(dates) if dates else pd.DataFrame(
        columns=["ts", "condition_id", "side", "price", "size", "notional_usd", "family", "outcome_index"])
    return compute_report(df, dates)


def main() -> None:
    rep = load_and_report()
    print(f"\n=== cost_bps(polymarket) = {rep['cost_bps']} ===\n")
    for g in rep["groups"]:
        if g["blocked"]:
            print(f"{g['group']} -> BLOCKED ({g['reason']})")
            continue
        for h in g["horizons"]:
            wf = h["walk_forward"]
            print(f"{g['group']}:{h['horizon']} n_events={h['n_events']} "
                  f"total_pnl={h['total_pnl']} p_value={h['p_value']} percentile={h['percentile']} "
                  f"wf_first={wf['wf_first']}(n={wf['n_first']}) wf_second={wf['wf_second']}(n={wf['n_second']}) "
                  f"wf_both_positive={wf['both_positive']}")
    for pool in rep["pools"]:
        print(f"\n=== BH-FDR (whale_coincidence 풀, alpha={pool['alpha']}) ===")
        print(f"survivors before walk-forward gate: {pool['survivors_before_walk_forward']}")
        print(f"survivors (BH-FDR + walk-forward both>0): {pool['survivors']}")
        print(f"n_survivors: {pool['n_survivors']} / {pool['n_tested']}")
    print(f"\nverdict: {rep['verdict']}")


if __name__ == "__main__":
    main()
