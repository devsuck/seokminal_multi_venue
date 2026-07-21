"""Polymarket MLB 스페셜리스트 컨센서스 검증 러너 — 다변형 BH-FDR 스크리닝, 실집행 없음.

변형 그리드 = {랭킹지표 pnl/winrate/roi} × {임계 majority/unanimous} × {N 4/5}.
각 변형의 컨센서스 신호 라벨(경기 정산까지 forward return)에서 방향 무작위 셔플
베이스라인 대비 empirical p-value를 구하고, **전 변형을 한 BH-FDR 풀로 보정**한다
(변형 골라잡기 = p-해킹 방지, 프로젝트 전역 규율). 다각화 봇 성과가 베이스라인.

⚠️ 스크리닝. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님. walk-forward로
스페셜리스트를 선정하되(look-ahead 차단), 신규 라이브 수집 직후엔 표본 미달 —
BH-FDR 통과 시 전체 파이프라인 승격 검토.

NOTE: raw 수집 데이터(트레이드/포지션 스냅샷/정산결과)를 walk-forward로 돌려
변형별 라벨(`variant_labels`)을 조립하는 `load_and_report()`는 수집기(Task 3)
데이터 포맷에 결합돼 있어 데이터 축적 후 맥에서 완성한다. 여기 `compute_report`는
변형별 라벨을 입력받는 순수 검증 코어(완전 테스트됨).
"""
from __future__ import annotations

import random as _random

import pandas as pd

from research.validation.baselines import empirical_p_value
from research.validation.cost_model import polymarket_effective_cost_bps
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/mlb_specialist"
RANKING_METRICS = ["pnl", "winrate", "roi"]
THRESHOLDS = ["majority", "unanimous"]
N_VALUES = [4, 5]
MIN_EVENTS = 10
N_RUNS = 500
SEED = 42
TRADE_SIZE = 1.0
COST_BPS = polymarket_effective_cost_bps()


def variant_key(metric: str, threshold: str, n: int) -> str:
    return f"{metric}:{threshold}:N{n}"


def enumerate_variants() -> list[str]:
    return [variant_key(m, t, n) for m in RANKING_METRICS for t in THRESHOLDS for n in N_VALUES]


def _variant_pvalue(labels: pd.DataFrame) -> tuple[dict, dict]:
    """라벨(entry_price/exit_price/direction)에서 실제 total_pnl vs 방향 셔플 베이스라인."""
    rng = _random.Random(SEED)
    precomputed = []
    for _, row in labels.iterrows():
        en, ex = float(row["entry_price"]), float(row["exit_price"])
        cost = (abs(en) + abs(ex)) * TRADE_SIZE * COST_BPS / 10_000.0
        precomputed.append((float(row["direction"]), en, ex, cost))
    actual = [d * (ex - en) * TRADE_SIZE - c for d, en, ex, c in precomputed]
    strat = trade_metrics([{"pnl": p} for p in actual])
    random_totals = []
    for _ in range(N_RUNS):
        total = 0.0
        for _d, en, ex, c in precomputed:
            total += rng.choice((1.0, -1.0)) * (ex - en) * TRADE_SIZE - c
        random_totals.append(round(total, 6))
    return strat, empirical_p_value(strat["total_pnl"], random_totals)


def compute_report(variant_labels: dict[str, pd.DataFrame]) -> dict:
    """변형별 라벨 dict → 변형별 p-value + 단일 BH-FDR 풀 + verdict. 순수함수."""
    variants: list[dict] = []
    pvals: list[float] = []
    keys: list[str] = []
    for key, labels in variant_labels.items():
        n = 0 if labels is None else len(labels)
        if n < MIN_EVENTS:
            variants.append({"variant": key, "blocked": True,
                             "reason": f"라벨 {n}건 — 최소 표본 미달"})
            continue
        strat, pval = _variant_pvalue(labels)
        variants.append({"variant": key, "blocked": False, "n_events": n,
                         "total_pnl": strat["total_pnl"], "p_value": pval["p_value"],
                         "percentile": pval["percentile"]})
        pvals.append(pval["p_value"])
        keys.append(key)

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1}
    survivors = [k for k, s in zip(keys, bh["survivors"]) if s]
    pool = {"name": "mlb_specialist_consensus", "alpha": bh["alpha"], "n_tested": len(pvals),
            "n_survivors": bh["n_survivors"], "survivors": survivors, "threshold": bh.get("threshold")}
    verdict = "no_data" if not pvals else ("candidate" if pool["n_survivors"] > 0 else "no_edge")
    return {"hypothesis": "mlb_specialist_consensus", "cost_bps": COST_BPS,
            "variants": variants, "pools": [pool], "verdict": verdict}


def main() -> None:
    # 데이터 조립(load_and_report)은 수집기 데이터 축적 후 맥에서 완성 — 위 NOTE 참고.
    print("MLB 스페셜리스트 검증 — 변형 그리드:")
    for v in enumerate_variants():
        print(f"  {v}")
    print(f"\ncost_bps(polymarket) = {COST_BPS}, MIN_EVENTS={MIN_EVENTS}, N_RUNS={N_RUNS}")
    print("데이터 조립(walk-forward)은 수집기 데이터 축적 후 연결 — compute_report는 준비 완료.")


if __name__ == "__main__":
    main()
