"""Polymarket 샤프월렛 컨버전스 가설 검증 러너 — 통계적 유의미성 스크리닝, 실집행 없음.

`research/run_polymarket_sharp_wallet_collect.py`가 쌓은 체결 원장
(research/data/polymarket_sharp_wallet/)을 읽어 컨버전스 버킷(1/2/3) x
다중호라이즌(30s/120s/300s) forward return을 계산하고,
`research/run_polymarket_whale_validate.py`와 동일하게 랜덤 베이스라인(방향
무작위 셔플) 대비 empirical p-value를 구한다. 최대 9개 p-value를 신규 독립
BH-FDR 풀로 correction한다.

2026-07-21: 버킷과 나란히 score tercile(연속 confidence score의 3분위) 검증도
추가 — `docs/superpowers/specs/2026-07-21-polymarket-sharp-wallet-scoring-design.md`.
score tercile은 버킷과 완전히 분리된 신규 BH-FDR 풀로 correction한다(다른
가설/축 p-value를 섞지 않는 프로젝트 전역 컨벤션).

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
    build_convergence_score,
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
SCORE_TERCILES = ["low", "mid", "high"]
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


def _score_horizons(group_labels: pd.DataFrame) -> dict[str, dict]:
    """group_labels(이미 버킷/티어사일로 필터링됨)의 horizon별 랜덤베이스라인
    p-value 계산 — run_bucket과 run_score_tercile이 공유하는 핵심 로직."""
    rng = _random.Random(SEED)
    horizons: dict[str, dict] = {}
    for h in sorted(group_labels["horizon_s"].unique()):
        sub = group_labels[group_labels["horizon_s"] == h]
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
    return horizons


def run_bucket(bucket: int, labels: pd.DataFrame) -> dict:
    bucket_labels = labels[labels["convergence_bucket"] == bucket]
    if bucket_labels.empty:
        return {"bucket": bucket, "blocked": True, "reason": "라벨 없음"}
    if len(bucket_labels) < MIN_EVENTS:
        return {"bucket": bucket, "blocked": True,
                "reason": f"라벨 {len(bucket_labels)}건뿐 — 최소 표본 미달"}
    return {"bucket": bucket, "blocked": False, "horizons": _score_horizons(bucket_labels)}


def add_score_tercile(labels: pd.DataFrame) -> pd.DataFrame:
    """labels(score 컬럼 포함)에 score_tercile("low"/"mid"/"high") 컬럼 추가.
    score가 전부 NaN이거나 고유값이 3개 미만이면(qcut으로 3등분 불가) 전부
    None으로 채운다 — run_score_tercile이 표본부족으로 BLOCKED 처리."""
    out = labels.copy()
    scores = out["score"]
    if scores.isna().all() or scores.nunique() < 3:
        out["score_tercile"] = None
        return out
    try:
        out["score_tercile"] = pd.qcut(scores, 3, labels=SCORE_TERCILES)
    except ValueError:
        out["score_tercile"] = None
    return out


def run_score_tercile(tercile: str, labels: pd.DataFrame) -> dict:
    tercile_labels = labels[labels["score_tercile"] == tercile]
    if tercile_labels.empty:
        return {"tercile": tercile, "blocked": True, "reason": "라벨 없음"}
    if len(tercile_labels) < MIN_EVENTS:
        return {"tercile": tercile, "blocked": True,
                "reason": f"라벨 {len(tercile_labels)}건뿐 — 최소 표본 미달"}
    return {"tercile": tercile, "blocked": False, "horizons": _score_horizons(tercile_labels)}


def _group_to_dict(gname: str, r: dict) -> tuple[dict, list[float], list[str]]:
    """run_bucket/run_score_tercile 결과 → 대시보드용 group dict + (pvals, keys) 기여분."""
    if r["blocked"]:
        return {"group": gname, "blocked": True, "reason": r.get("reason", "")}, [], []
    horizons, pvals, keys = [], [], []
    for hk, hv in r["horizons"].items():
        horizons.append({"horizon": hk, "n_events": hv["n_events"],
                         "total_pnl": hv["strategy"]["total_pnl"],
                         "p_value": hv["random"]["p_value"], "percentile": hv["random"]["percentile"]})
        pvals.append(hv["random"]["p_value"])
        keys.append(f"{gname}:{hk}")
    return {"group": gname, "blocked": False, "horizons": horizons}, pvals, keys


def _pool_dict(name: str, pvals: list[float], keys: list[str]) -> dict:
    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1}
    survivors = [k for k, s in zip(keys, bh["survivors"]) if s]
    return {"name": name, "alpha": bh["alpha"], "n_tested": len(pvals),
            "n_survivors": bh["n_survivors"], "survivors": survivors, "threshold": bh.get("threshold")}


def compute_report(trades: pd.DataFrame, dates: list[str]) -> dict:
    """검증 결과를 대시보드/CLI 공용 dict로 반환 — 신규 통계 없음, 기존 run_* 재사용.
    버킷 풀과 score tercile 풀을 분리 유지. anchors 없으면 verdict='no_data'."""
    anchors = build_convergence_count(trades)
    if anchors.empty:
        return {"hypothesis": "polymarket_sharp_wallet", "cost_bps": COST_BPS, "dates": dates,
                "n_anchors": 0, "groups": [], "pools": [], "verdict": "no_data"}
    anchors = build_convergence_score(trades, anchors)
    price_by_condition = {
        cid: build_price_series(trades, cid) for cid in anchors["condition_id"].unique()
    }
    labels = add_score_tercile(build_labels_multi_horizon(anchors, price_by_condition))

    groups: list[dict] = []
    b_pvals: list[float] = []
    b_keys: list[str] = []
    for bucket in CONVERGENCE_BUCKETS:
        g, pv, ks = _group_to_dict(f"bucket{bucket}", run_bucket(bucket, labels))
        groups.append(g)
        b_pvals += pv
        b_keys += ks

    t_pvals: list[float] = []
    t_keys: list[str] = []
    for tercile in SCORE_TERCILES:
        g, pv, ks = _group_to_dict(tercile, run_score_tercile(tercile, labels))
        groups.append(g)
        t_pvals += pv
        t_keys += ks

    pools = [_pool_dict("bucket", b_pvals, b_keys), _pool_dict("score_tercile", t_pvals, t_keys)]
    n_surv = sum(p["n_survivors"] for p in pools)
    return {"hypothesis": "polymarket_sharp_wallet", "cost_bps": COST_BPS, "dates": dates,
            "n_anchors": int(len(anchors)), "groups": groups, "pools": pools,
            "verdict": "candidate" if n_surv > 0 else "no_edge"}


def load_and_report() -> dict:
    """디스크에서 수집 데이터 로드 후 compute_report. 엔드포인트/main 공용 진입점."""
    dates = _available_dates()
    trades = load_sharp_wallet_trades(dates) if dates else pd.DataFrame(columns=[
        "ts", "condition_id", "side", "price", "size", "proxy_wallet",
        "notional_usd", "is_sharp_wallet", "wallet_rank", "wallet_pnl",
    ])
    return compute_report(trades, dates)


def main() -> None:
    rep = load_and_report()
    print(f"\n=== cost_bps(polymarket) = {rep['cost_bps']} ===\n")
    for g in rep["groups"]:
        if g["blocked"]:
            print(f"{g['group']} -> BLOCKED ({g['reason']})")
            continue
        for h in g["horizons"]:
            print(f"{g['group']}:{h['horizon']} n_events={h['n_events']} "
                  f"total_pnl={h['total_pnl']} p_value={h['p_value']} percentile={h['percentile']}")
    for pool in rep["pools"]:
        label = ("신규 Polymarket sharp-wallet 풀" if pool["name"] == "bucket"
                 else "score tercile 풀, 버킷 풀과 분리")
        print(f"\n=== BH-FDR ({label}, alpha={pool['alpha']}) ===")
        print(f"survivors: {pool['survivors']}")
        print(f"n_survivors: {pool['n_survivors']} / {pool['n_tested']}")
    print(f"\nverdict: {rep['verdict']}")


if __name__ == "__main__":
    main()
