"""Polymarket whale tracking 가설 검증 러너 — 통계적 유의미성 스크리닝, 실집행 없음.

`research/run_polymarket_whale_collect.py`가 쌓은 체결 원장(research/data/polymarket_whale/)을
읽어 마켓별 notional z-score 스파이크(고래 체결) -> 다중호라이즌(30s/120s/300s)
forward return을 계산하고, `research/run_cross_venue_skew_validate.py`와 동일하게
랜덤 베이스라인(체결 방향 무작위 셔플) 대비 empirical p-value를 구한다. family
(news/sports) x 호라이즌3 = 최대 6개 p-value를 신규 독립 BH-FDR 풀로 correction한다.
호라이즌별 walk-forward(전반/후반 시간순 2분할, `research/lab/evaluator.py`·`research/run_tsmom.py`와
동일 idiom, wf_first/wf_second 키는 `jarvis/agents/critic.py` 승격기준과 정렬)도 같이 게이트한다.

⚠️ 스크리닝 스크립트. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님. BH-FDR survivor라도
walk-forward 양쪽 구간이 다 양수여야 최종 verdict의 candidate에 반영됨(p-hacking 방지 위해
BH-FDR 자체는 전체 pvals로 correction, walk-forward는 그 위에 얹는 별도 게이트).
"""
from __future__ import annotations

import glob
import random as _random
import re

import pandas as pd

from research.hypotheses.polymarket_whale import (
    build_labels_multi_horizon,
    build_notional_zscore,
    build_price_series,
    build_spike_signal,
    load_whale_trades,
)
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


def _walk_forward(precomputed: list[tuple]) -> dict:
    """시간순 전반/후반 2분할 PnL 부호 게이트 — `research/lab/evaluator.py`/`research/run_tsmom.py`
    idiom 재사용. precomputed는 이미 sub(호라이즌 서브셋, ts 오름차순)에서 만들어져 시간순 유지."""
    n = len(precomputed)
    mid = n // 2

    def _pnl(chunk):
        return round(sum(d * (ex - en) * TRADE_SIZE - c for d, en, ex, c in chunk), 6)

    first, second = _pnl(precomputed[:mid]), _pnl(precomputed[mid:])
    return {"wf_first": first, "wf_second": second, "n_first": mid, "n_second": n - mid,
            "both_positive": first > 0 and second > 0}


def _available_dates() -> list[str]:
    dates = set()
    for path in glob.glob(f"{DATA_DIR}/*.jsonl"):
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.jsonl$", path)
        if m:
            dates.add(m.group(1))
    return sorted(dates)


def run_family(family: str, df: pd.DataFrame) -> dict:
    fam_df = df[df["family"] == family]
    if fam_df.empty:
        return {"family": family, "blocked": True, "reason": "데이터 없음"}

    df_z = build_notional_zscore(fam_df)
    spikes = build_spike_signal(df_z)
    if spikes.empty:
        return {"family": family, "blocked": True, "reason": "스파이크 이벤트 없음"}

    price_by_condition = {
        cid: build_price_series(fam_df, cid) for cid in spikes["condition_id"].unique()
    }
    labels = build_labels_multi_horizon(price_by_condition, spikes)

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
    """run_family 결과 → 대시보드용 group dict + (pvals, keys, key→walk_forward_both_positive) 기여분."""
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
    """검증 결과를 대시보드/CLI 공용 dict로 반환 — 신규 통계 없음, run_family 재사용.
    whale은 단일 BH-FDR 풀(family×horizon). df 비면 verdict='no_data'."""
    if df.empty:
        return {"hypothesis": "polymarket_whale", "cost_bps": COST_BPS, "dates": dates,
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
    pool = {"name": "whale", "alpha": bh["alpha"], "n_tested": len(pvals),
            "n_survivors": len(survivors), "survivors": survivors,
            "survivors_before_walk_forward": survivors_raw, "threshold": bh.get("threshold")}
    return {"hypothesis": "polymarket_whale", "cost_bps": COST_BPS, "dates": dates,
            "n_anchors": n_labels, "groups": groups, "pools": [pool],
            "verdict": "candidate" if pool["n_survivors"] > 0 else "no_edge"}


def load_and_report() -> dict:
    """디스크에서 수집 데이터 로드 후 compute_report. 엔드포인트/main 공용 진입점."""
    dates = _available_dates()
    df = load_whale_trades(dates) if dates else pd.DataFrame(
        columns=["ts", "condition_id", "side", "price", "size", "notional_usd", "family"])
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
        print(f"\n=== BH-FDR (신규 Polymarket whale 풀, alpha={pool['alpha']}) ===")
        print(f"survivors before walk-forward gate: {pool['survivors_before_walk_forward']}")
        print(f"survivors (BH-FDR + walk-forward both>0): {pool['survivors']}")
        print(f"n_survivors: {pool['n_survivors']} / {pool['n_tested']}")
    print(f"\nverdict: {rep['verdict']}")


if __name__ == "__main__":
    main()
