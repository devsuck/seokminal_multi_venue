"""KR buyback 사이징 variant 비교 — 필터형 vs 연속가중형, 둘 다 사전등록 동시테스트.
v1(next_open/HOLD20/균등비중) 동결, 청산룰 안 건드림 — 포지션 "크기"만 신호(금액/ADV)로 조절.

배경(run_buyback_size_decomp.py): 금액/ADV 분위 단조— 하위25% mean-0.12%, 중간50% +1.04%,
상위25% +2.51%. 금액/시총은 신호 지저분해서 기각, ADV비율만 사용.

filter_top25: 금액/ADV 상위25%만 진입(나머지 비중 0) — net 올리지만 동시슬롯 줄어듦
weighted_rank: 전량 진입, 비중 = rank/(n+1) (0~1 연속, 낮은 순위도 소량 유지) — 슬롯 유지, net 완만히 개선

공통 제약: plan_amount(취득예정금액) DART 상세 있는 이벤트만 대상(전체 아님) — 두 variant 같은
분모(n)로 공정비교. weight는 순위 기반(퍼센타일)이라 값 자체 이상치에 민감 안 함.
random 대조: 같은 weight_i를 유지한 채 (stock,day)만 무작위 치환 — "이 가중치 패턴이 buyback
신호 자체에서 오는 초과분"을 분리.
실행: PYTHONPATH=. python3 research/run_buyback_sizing_variants.py
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


def _load_rows():
    """buyback 이벤트 중 금액/ADV ratio 계산 가능한 것만 → [(date, code, j, ratio)]."""
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
        if not amt or adv <= 0:
            continue
        rows.append({"date": e["date"], "code": e["stock_code"], "bars": b, "j": j, "ratio": amt / adv})
    return rows, series


def _assign_weights(rows):
    n = len(rows)
    ranked = sorted(range(n), key=lambda i: rows[i]["ratio"])
    for rank, i in enumerate(ranked):
        pct = (rank + 1) / n  # (0, 1], 낮은 ratio도 소량 가중 유지
        rows[i]["pct_rank"] = pct
        rows[i]["w_filter25"] = 1.0 if pct >= 0.75 else 0.0
        rows[i]["w_weighted"] = pct


def _weighted_net(rows, wkey, cost_rt):
    num = 0.0; den = 0.0
    for r in rows:
        w = r[wkey]
        if w <= 0:
            continue
        ret = _fwd(r["bars"], r["j"], cost_rt)
        if ret is None:
            continue
        num += w * ret; den += w
    return (num / den) if den > 0 else None, den


def _random_weighted_net(rows, wkey, cost_rt, pool, rng):
    num = 0.0; den = 0.0
    for r in rows:
        w = r[wkey]
        if w <= 0:
            continue
        b, j = pool[rng.randrange(len(pool))]
        ret = _fwd(b, j, cost_rt)
        num += w * (ret if ret is not None else 0.0); den += w
    return (num / den) if den > 0 else 0.0


def _run_variant(name, wkey, rows, pool):
    print("\n" + "-" * 70)
    active_n = sum(1 for r in rows if r[wkey] > 0)
    print(f"[{name}] 유효슬롯(w>0) n={active_n} / 전체후보 n={len(rows)}")

    results = {}
    for cname, rt in COST_LEVELS.items():
        bnet, den = _weighted_net(rows, wkey, rt)
        if bnet is None:
            print("  매칭 0"); return None
        rng = _random.Random(SEED); rmeans = []
        for _ in range(N_RUNS):
            rmeans.append(_random_weighted_net(rows, wkey, rt, pool, rng))
        pv = empirical_p_value(bnet, rmeans)
        results[cname] = {"net": round(bnet, 6), "pct": pv["percentile"], "p": pv["p_value"], "med": pv["random_median"]}
        print(f"  [{cname}] net={bnet:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    mid = len(rows_sorted) // 2
    fh, _ = _weighted_net(rows_sorted[:mid], wkey, COST_LEVELS["base_20bps"])
    sh, _ = _weighted_net(rows_sorted[mid:], wkey, COST_LEVELS["base_20bps"])
    fh = fh or 0.0; sh = sh or 0.0
    print(f"  walk-forward(base): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    base = results["base_20bps"]
    passed = (base["net"] > 0 and (base["pct"] or 0) >= 95 and (base["p"] or 1) < 0.05
              and fh > 0 and sh > 0 and results["stress_50bps"]["net"] > 0)
    verdict = ("WATCHLIST→PAPER 후보 — PIT 통과" if passed else
               "WEAK — random 80~95pct" if (base["net"] > 0 and (base["pct"] or 0) >= 80) else
               "REJECT — 매칭 random·비용 못 넘음")
    print(f"  VERDICT: {verdict}")

    log_experiment({"hypothesis_id": f"kr_dart_buyback_sizing_{name}_v2_PIT",
                    "status": "watchlist" if "WATCHLIST" in verdict else "rejected" if "REJECT" in verdict else "underpowered",
                    "variant": name, "trade_count": active_n, "net_base": base["net"], "percentile": base["pct"], "p": base["p"],
                    "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "cost_stress": {k: v["net"] for k, v in results.items()},
                    "data_quality": "PIT + survivorship-free (KRX 스냅샷), split-adjust 완료",
                    "verdict": verdict,
                    "note": f"사이징variant({name}, 금액/ADV 기반 가중) — v1(next_open/HOLD20) 동결, 청산룰 불변, 비중만 조절"})
    return base["net"], verdict


def main():
    print("=" * 74 + "\nKR BUYBACK 사이징 VARIANT 비교 (필터형 vs 연속가중형, 금액/ADV 기반)\n" + "=" * 74)
    rows, series = _load_rows()
    _assign_weights(rows)
    pool = _random_pool(series)
    print(f"ratio 계산 가능 이벤트 n={len(rows)}")

    eq_net, _ = _weighted_net([{**r, "w_eq": 1.0} for r in rows], "w_eq", COST_LEVELS["base_20bps"])
    print(f"(참고) 같은 n={len(rows)}에서 균등비중(v1 동일) net={eq_net:+.4f} — 필터/가중 효과 비교 기준선")

    summary = {}
    for name, wkey in [("filter25adv", "w_filter25"), ("weightrank_adv", "w_weighted")]:
        res = _run_variant(name, wkey, rows, pool)
        if res:
            summary[name] = res

    print("\n" + "=" * 74)
    print(f"요약 (균등비중 기준선 net={eq_net:+.4f})")
    for name, (net, verdict) in summary.items():
        print(f"  {name:16} net={net:+.4f}  {verdict}")


if __name__ == "__main__":
    main()
