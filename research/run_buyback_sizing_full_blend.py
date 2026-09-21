"""KR buyback 사이징 전체유니버스 blend 테스트 — v2 사이징 트랙 최종 게이트.
사전등록: DART plan_amount 상세 없는 이벤트는 weight=1(v1 동일, 디폴트) 유지,
있는 이벤트만 금액/ADV pct_rank(0,1]로 가중. n=1978 전체 기준 blended net이
순수v1 net(+0.0175)을 못 넘으면 이 ADV비율 사이징 신호는 기각.

배경: run_buyback_sizing_variants.py의 weightrank_adv(net+1.66%, n=569)는
detail 있는 서브셋(자체 기준선 net+1.11%, 전체보다 약한 그룹) 안에서만 계산된
값이라 전체v1(+1.75%, n=1978)과 직접비교 불가했음 — 이 스크립트가 그 비교를 한다.
실행: PYTHONPATH=. python3 research/run_buyback_sizing_full_blend.py
"""
from __future__ import annotations

import bisect
import random as _random
import statistics as _st
import glob, os

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events, pull_buyback_details
from research.validation.baselines import empirical_p_value
from research.agents.experiment_registry import log_experiment
from research.paper import buyback_config as CFG

HOLD = CFG.HOLD_DAYS
COST_LEVELS = {"base_20bps": 40.0, "stress_50bps": 100.0}
N_RUNS = 500
SEED = 42


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _entry_idx(bars, event_date):
    j = bisect.bisect_right(bars["dates"], event_date)
    if j >= len(bars["dates"]) or bars["open"][j] <= 0:
        return None
    return j


def _fwd(bars, j, cost_rt):
    entry = bars["open"][j]
    xi = min(j + HOLD, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return (bars["close"][xi] / entry - 1) - cost_rt / 10_000.0


def _random_pool(series):
    pool = []
    for b in series.values():
        for j in range(len(b["dates"]) - HOLD - 1):
            pool.append((b, j + 1))
    return pool


def _load_all_rows():
    """전체 buyback 이벤트(매칭 가능한 전부) → [{date,bars,j,ratio|None}]."""
    events = load_events("buyback")
    corps = sorted({e["corp_code"] for e in events if e.get("corp_code")})
    details = pull_buyback_details(corps, "20240101", "20260921")
    dmap = {(d["corp_code"], d["rcept_dt"]): d for d in details}

    series = _series()
    rows = []
    for e in events:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        j = _entry_idx(b, e["date"])
        if j is None:
            continue
        j0 = j - 1
        adv = _st.mean(b["tval"][max(0, j0 - 20):j0]) if j0 >= 5 else 0
        d = dmap.get((e["corp_code"], e["date"].replace("-", "")))
        amt = d.get("plan_amount") if d else None
        ratio = (amt / adv) if (amt and adv > 0) else None
        rows.append({"date": e["date"], "bars": b, "j": j, "ratio": ratio})
    return rows, series


def _assign_blend_weights(rows):
    """detail 있는 이벤트만 pct_rank(0,1], 없는 이벤트는 1.0(v1 디폴트) 고정."""
    have = [i for i, r in enumerate(rows) if r["ratio"] is not None]
    ranked = sorted(have, key=lambda i: rows[i]["ratio"])
    n = len(ranked)
    for rank, i in enumerate(ranked):
        rows[i]["w_blend"] = (rank + 1) / n
    for r in rows:
        if r["ratio"] is None:
            r["w_blend"] = 1.0


def _weighted_net(rows, cost_rt):
    num = 0.0; den = 0.0
    for r in rows:
        w = r["w_blend"]
        ret = _fwd(r["bars"], r["j"], cost_rt)
        if ret is None:
            continue
        num += w * ret; den += w
    return (num / den) if den > 0 else None


def _random_weighted_net(rows, cost_rt, pool, rng):
    num = 0.0; den = 0.0
    for r in rows:
        w = r["w_blend"]
        b, j = pool[rng.randrange(len(pool))]
        ret = _fwd(b, j, cost_rt)
        num += w * (ret if ret is not None else 0.0); den += w
    return (num / den) if den > 0 else 0.0


def main():
    print("=" * 74 + "\nKR BUYBACK 사이징 전체유니버스 BLEND (detail無=weight1 디폴트, 사전등록)\n" + "=" * 74)
    rows, series = _load_all_rows()
    _assign_blend_weights(rows)
    pool = _random_pool(series)
    n_have = sum(1 for r in rows if r["ratio"] is not None)
    print(f"전체 매칭 n={len(rows)} (그중 detail 有={n_have}, 無={len(rows)-n_have} → weight=1)")

    results = {}
    for cname, rt in COST_LEVELS.items():
        bnet = _weighted_net(rows, rt)
        rng = _random.Random(SEED); rmeans = []
        for _ in range(N_RUNS):
            rmeans.append(_random_weighted_net(rows, rt, pool, rng))
        pv = empirical_p_value(bnet, rmeans)
        results[cname] = {"net": round(bnet, 6), "pct": pv["percentile"], "p": pv["p_value"], "med": pv["random_median"]}
        print(f"  [{cname}] net={bnet:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    mid = len(rows_sorted) // 2
    fh = _weighted_net(rows_sorted[:mid], COST_LEVELS["base_20bps"])
    sh = _weighted_net(rows_sorted[mid:], COST_LEVELS["base_20bps"])
    print(f"  walk-forward(base): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    base = results["base_20bps"]
    V1_NET = 0.0175
    beats_v1 = base["net"] > V1_NET
    passed = (base["net"] > 0 and (base["pct"] or 0) >= 95 and (base["p"] or 1) < 0.05
              and fh > 0 and sh > 0 and results["stress_50bps"]["net"] > 0 and beats_v1)
    verdict = ("ACCEPT — v1 대비 전체유니버스에서 개선 확인" if passed else
               f"REJECT — 전체유니버스 net({base['net']:+.4f}) v1 기준선(+{V1_NET:.4f}) 못 넘음" if not beats_v1 else
               "WEAK — v1은 넘었으나 PIT 기준 미충족")
    print(f"\n  순수v1 기준선: +{V1_NET:.4f} (n=1978)")
    print(f"  VERDICT: {verdict}")

    log_experiment({"hypothesis_id": "kr_dart_buyback_sizing_fulluniverse_blend_v2_PIT",
                    "status": "watchlist" if passed else "rejected",
                    "variant": "fulluniverse_blend", "trade_count": len(rows), "net_base": base["net"],
                    "percentile": base["pct"], "p": base["p"],
                    "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "cost_stress": {k: v["net"] for k, v in results.items()},
                    "data_quality": "PIT + survivorship-free (KRX 스냅샷), split-adjust 완료",
                    "verdict": verdict,
                    "note": "detail無 weight=1 디폴트 + detail有 pct_rank 가중, 전체n=1978 기준 v1(+1.75%)과 직접비교 — 사이징트랙 최종게이트"})


if __name__ == "__main__":
    main()
