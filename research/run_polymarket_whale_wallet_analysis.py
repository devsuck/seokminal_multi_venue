"""Polymarket whale 지갑 역추적 분석 — "누가 큰 거래를 쳤는지" 두 방향으로 검증.

배경: run_polymarket_whale_validate.py의 순수 사이즈 z-score 시그널은 9일간
edge_history 기준 거의 no_edge(203/207)였다. whale 원장 raw jsonl엔 이미
proxyWallet이 있었는데 로더가 버리고 있었을 뿐 — hypotheses/polymarket_whale.py에
proxy_wallet 컬럼을 추가해 지갑 정체를 신호에 실어본다.

1) leaderboard 교차조회 — polymarket_sharp_wallet.leaderboard의 공식 랭킹
   지갑 집합과 whale 스파이크 지갑을 교차해 "큰 거래 + 검증된 실력자"만 남긴
   서브셋(leaderboard_wallet)이 나머지(other_wallet)보다 나은지 검증.
2) self-referential 지갑 스코어 — 리더보드 등재 여부와 무관하게, whale
   원장 자체에서 지갑별 "이 이벤트 이전까지의" 평균 forward_return을
   prequential(과거 데이터만, lookahead 없음)로 계산해 스코어로 쓰고,
   상위 스코어 지갑(top_score_wallet)이 나머지(rest_wallet)보다 나은지 검증.

두 축은 서로 다른 신규 독립 BH-FDR 풀로 correction한다(프로젝트 전역
컨벤션 — 다른 가설/축 p-value를 섞지 않음). 각 풀 내부는 run_ict.py와
동일한 walk-forward 컨벤션(시간순 반분, 전반/후반 둘 다 양수)으로 추가 게이트.

⚠️ 스크리닝 스크립트. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님.
"""
from __future__ import annotations

import random as _random

import pandas as pd

from research.agents.experiment_registry import log_experiment
from research.hypotheses.polymarket_whale import (
    build_labels_multi_horizon,
    build_notional_zscore,
    build_price_series,
    build_spike_signal,
    load_whale_trades,
)
from research.polymarket_sharp_wallet.leaderboard import build_sharp_wallet_set, fetch_leaderboard
from research.run_polymarket_whale_validate import (
    COST_BPS,
    MIN_EVENTS,
    N_RUNS,
    SEED,
    TRADE_SIZE,
    _available_dates,
)
from research.validation.baselines import empirical_p_value
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

HYPOTHESIS_ID_LEADERBOARD = "polymarket_whale_leaderboard_wallet_v1"
HYPOTHESIS_ID_SELFSCORE = "polymarket_whale_selfscore_wallet_v1"
MIN_PRIOR_TRADES = 3       # self-referential 스코어 계산에 필요한 최소 과거 표본
TOP_SCORE_FRACTION = 0.3   # 상위 지갑 스코어 컷(상위 30%)


def _build_all_labels(dates: list[str]) -> pd.DataFrame:
    """whale 원장 전체(family 구분 없이) -> notional z-score -> spike -> labels.
    run_polymarket_whale_validate.run_family와 동일 파이프라인이나 family로
    쪼개지 않고 한번에(지갑 축은 family와 독립 질문이라)."""
    df = load_whale_trades(dates) if dates else pd.DataFrame()
    if df.empty:
        return pd.DataFrame()
    df_z = build_notional_zscore(df)
    spikes = build_spike_signal(df_z)
    if spikes.empty:
        return pd.DataFrame()
    price_by_condition = {cid: build_price_series(df, cid) for cid in spikes["condition_id"].unique()}
    return build_labels_multi_horizon(price_by_condition, spikes)


def _score_horizon_subset(sub: pd.DataFrame) -> dict:
    """단일 (그룹, horizon) 서브셋 -> 랜덤베이스라인 p-value + walk-forward.
    run_polymarket_sharp_wallet_validate._score_horizons와 동일 idiom."""
    rng = _random.Random(SEED)
    precomputed = []
    for _, row in sub.iterrows():
        entry_px, exit_px = row["entry_price"], row["exit_price"]
        cost = (abs(entry_px) + abs(exit_px)) * TRADE_SIZE * COST_BPS / 10_000.0
        precomputed.append((row["direction"], entry_px, exit_px, cost))

    actual_pnls = [d * (ex - en) * TRADE_SIZE - c for d, en, ex, c in precomputed]
    strat = trade_metrics([{"pnl": p} for p in actual_pnls])

    random_totals = []
    for _ in range(N_RUNS):
        total = 0.0
        for _d, en, ex, c in precomputed:
            rsign = rng.choice((1.0, -1.0))
            total += rsign * (ex - en) * TRADE_SIZE - c
        random_totals.append(round(total, 6))
    pval = empirical_p_value(strat["total_pnl"], random_totals)

    mid = len(actual_pnls) // 2
    first, second = actual_pnls[:mid], actual_pnls[mid:]
    wf1 = sum(first) / len(first) if first else None
    wf2 = sum(second) / len(second) if second else None
    wf_pass = wf1 is not None and wf2 is not None and wf1 > 0 and wf2 > 0

    return {"n_events": len(sub), "total_pnl": strat["total_pnl"], "p_value": pval["p_value"],
            "percentile": pval["percentile"],
            "wf_first": round(wf1, 6) if wf1 is not None else None,
            "wf_second": round(wf2, 6) if wf2 is not None else None, "wf_pass": wf_pass}


def _run_pool(name: str, groups: dict[str, pd.DataFrame]) -> dict:
    """groups: gname -> 라벨 서브셋. horizon별로 쪼개 채점 후 그룹x호라이즌
    전체를 신규 단일 BH-FDR 풀로 correction, survivor는 walk-forward로 추가 게이트."""
    result_groups = []
    pvals: list[float] = []
    keys: list[str] = []
    horizon_by_key: dict[str, dict] = {}

    for gname, glabels in groups.items():
        if glabels.empty or len(glabels) < MIN_EVENTS:
            result_groups.append({"group": gname, "blocked": True,
                                   "reason": f"라벨 {len(glabels)}건뿐 — 최소 표본({MIN_EVENTS}) 미달"})
            continue
        horizons = []
        for h in sorted(glabels["horizon_s"].unique()):
            sub = glabels[glabels["horizon_s"] == h]
            r = _score_horizon_subset(sub)
            key = f"{gname}:{int(h)}s"
            horizons.append({"horizon": f"{int(h)}s", **r})
            pvals.append(r["p_value"])
            keys.append(key)
            horizon_by_key[key] = r
        result_groups.append({"group": gname, "blocked": False, "horizons": horizons})

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1}
    survivors = [k for k, s in zip(keys, bh["survivors"]) if s]
    wf_results = [horizon_by_key[k] for k in survivors]
    n_wf_pass = sum(1 for h in wf_results if h["wf_pass"])
    wf_all_pass = bool(wf_results) and n_wf_pass == len(wf_results)

    if bh["n_survivors"] == 0:
        verdict = "no_edge"
    elif wf_all_pass:
        verdict = "candidate"
    else:
        verdict = "paper_candidate_forward_test_required"

    return {"pool": name, "blocked": False, "groups": result_groups, "alpha": bh["alpha"],
            "n_tested": len(pvals), "n_survivors": bh["n_survivors"], "survivors": survivors,
            "n_wf_pass": n_wf_pass, "n_wf_tested": len(wf_results), "verdict": verdict}


def run_leaderboard_crosscheck(labels: pd.DataFrame) -> dict:
    """1) whale 스파이크 지갑을 공식 리더보드(top50 전체기간 PnL)와 교차조회."""
    entries = fetch_leaderboard()
    sharp_set = build_sharp_wallet_set(entries)
    if not sharp_set:
        return {"pool": "whale_x_leaderboard", "blocked": True, "reason": "리더보드 응답 없음/빈 목록"}
    is_sharp = labels["proxy_wallet"].apply(lambda w: bool(w) and w in sharp_set)
    groups = {"leaderboard_wallet": labels[is_sharp], "other_wallet": labels[~is_sharp]}
    return _run_pool("whale_x_leaderboard", groups)


def _prequential_wallet_score(labels: pd.DataFrame) -> pd.Series:
    """지갑별 "이 이벤트 이전까지"의 평균 forward_return — lookahead 없는
    prequential 스코어. 같은 실제 체결이 horizon 3개로 나뉜 행이라도 ts 오름차순
    순회이므로 미래 정보 유입은 없다(과거 자기 자신의 다른 horizon 행도 미포함,
    ts 동일 행은 sort_values 안정정렬로 원순서 유지). 지갑당 과거표본
    MIN_PRIOR_TRADES 미만이면 NaN(스코어링 불가)."""
    out = pd.Series(index=labels.index, dtype=float)
    ordered = labels.sort_values("ts")
    running: dict[str, list[float]] = {}
    for idx, row in ordered.iterrows():
        w = row["proxy_wallet"]
        if not w:
            out.loc[idx] = float("nan")
            continue
        history = running.setdefault(w, [])
        out.loc[idx] = sum(history) / len(history) if len(history) >= MIN_PRIOR_TRADES else float("nan")
        history.append(row["forward_return"])
    return out


def run_self_referential(labels: pd.DataFrame) -> dict:
    """2) 리더보드 무관 — whale 원장 자체 과거 성적으로 지갑 스코어 매겨 상위/하위 분리."""
    scored = labels.copy()
    scored["prior_score"] = _prequential_wallet_score(scored)
    scorable = scored.dropna(subset=["prior_score"])
    if scorable.empty:
        return {"pool": "whale_selfscore", "blocked": True,
                "reason": "지갑당 과거표본 부족 — 반복 등장 지갑 없음"}
    cutoff = scorable["prior_score"].quantile(1 - TOP_SCORE_FRACTION)
    groups = {"top_score_wallet": scorable[scorable["prior_score"] >= cutoff],
              "rest_wallet": scorable[scorable["prior_score"] < cutoff]}
    return _run_pool("whale_selfscore", groups)


def main() -> None:
    dates = _available_dates()
    labels = _build_all_labels(dates)
    if labels.empty:
        print("라벨 없음 — whale 스파이크 이벤트 자체가 없음. 종료.")
        return

    n_total = len(labels)
    n_with_wallet = int(labels["proxy_wallet"].notna().sum())
    print(f"labels total={n_total}, proxy_wallet 있음={n_with_wallet}")

    print("\n=== 1) leaderboard 교차조회 ===")
    lb = run_leaderboard_crosscheck(labels)
    if lb.get("blocked"):
        print(f"BLOCKED: {lb['reason']}")
    else:
        for g in lb["groups"]:
            if g["blocked"]:
                print(f"{g['group']} -> BLOCKED ({g['reason']})")
                continue
            for h in g["horizons"]:
                print(f"{g['group']}:{h['horizon']} n_events={h['n_events']} total_pnl={h['total_pnl']} "
                      f"p_value={h['p_value']} wf_first={h['wf_first']} wf_second={h['wf_second']} "
                      f"wf_pass={h['wf_pass']}")
        print(f"survivors: {lb['survivors']} ({lb['n_survivors']}/{lb['n_tested']}), "
              f"wf_pass={lb['n_wf_pass']}/{lb['n_wf_tested']}, verdict={lb['verdict']}")
        log_experiment({
            "hypothesis_id": HYPOTHESIS_ID_LEADERBOARD, "status": lb["verdict"],
            "n_tested": lb["n_tested"], "n_survivors": lb["n_survivors"],
            "n_wf_pass": lb["n_wf_pass"], "n_wf_tested": lb["n_wf_tested"],
            "dates": dates, "survivors": lb["survivors"],
            "note": "whale 스파이크 지갑 vs 공식 polymarket 리더보드(top50 전체기간 PnL) 교차조회",
        })

    print("\n=== 2) self-referential 지갑 스코어 ===")
    sr = run_self_referential(labels)
    if sr.get("blocked"):
        print(f"BLOCKED: {sr['reason']}")
    else:
        for g in sr["groups"]:
            if g["blocked"]:
                print(f"{g['group']} -> BLOCKED ({g['reason']})")
                continue
            for h in g["horizons"]:
                print(f"{g['group']}:{h['horizon']} n_events={h['n_events']} total_pnl={h['total_pnl']} "
                      f"p_value={h['p_value']} wf_first={h['wf_first']} wf_second={h['wf_second']} "
                      f"wf_pass={h['wf_pass']}")
        print(f"survivors: {sr['survivors']} ({sr['n_survivors']}/{sr['n_tested']}), "
              f"wf_pass={sr['n_wf_pass']}/{sr['n_wf_tested']}, verdict={sr['verdict']}")
        log_experiment({
            "hypothesis_id": HYPOTHESIS_ID_SELFSCORE, "status": sr["verdict"],
            "n_tested": sr["n_tested"], "n_survivors": sr["n_survivors"],
            "n_wf_pass": sr["n_wf_pass"], "n_wf_tested": sr["n_wf_tested"],
            "dates": dates, "survivors": sr["survivors"],
            "note": f"prequential 지갑 자체스코어(과거평균 forward_return, min_prior={MIN_PRIOR_TRADES}), "
                    f"top{TOP_SCORE_FRACTION:.0%} vs 나머지",
        })


if __name__ == "__main__":
    main()
