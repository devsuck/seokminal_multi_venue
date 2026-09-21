"""KR buyback 청산룰 variant 비교 — v1(HOLD20 고정) 동결, 별도 사전등록 v2 후보 검증.

배경(run_buyback_exit_mfe.py 진단): final(20일) median +0.63% vs MFE(보유중최고점) median +6.37%,
mean_day=9.7 — 20일까지 들고 가면 초반 랠리 절반 이상 반납. 익절 못하는 구조가 원인 후보.

v2-a: 고정홀딩 10일 (mean_day 근거)
v2-b: 타겟엑싯 +5% 닿으면 즉시청산, 아니면 20일차 청산 (target=5%는 diagnostic MFE median 아래로
      pre-set — walk-forward 2분할로 과최적 여부 확인)

v1과 동일 검증: PIT, random matched N_RUNS=500, walk-forward, cost stress. 랜덤풀도 각 variant와
동일 청산룰 적용(공정비교). 각 variant hypothesis_id 별도로 ledger 기록. v1 파일(run_kr_dart_buyback_pit.py)
불변.
실행: PYTHONPATH=. python3 research/run_buyback_exit_variants.py
"""
from __future__ import annotations

import bisect
import random as _random
import statistics as _st
import glob, os

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events
from research.validation.baselines import empirical_p_value
from research.agents.experiment_registry import log_experiment

COST_LEVELS = {"base_20bps": 40.0, "stress_50bps": 100.0}
N_RUNS = 500
SEED = 42

HOLD_A = 10
TARGET_B = 0.05
MAX_HOLD_B = 20


def _load_all_series() -> dict:
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _entry_idx(bars, event_date):
    j = bisect.bisect_right(bars["dates"], event_date)
    if j >= len(bars["dates"]) or bars["open"][j] <= 0:
        return None
    return j


def _exit_fixed(bars, j, hold, cost_rt):
    entry = bars["open"][j]
    xi = min(j + hold, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return (bars["close"][xi] / entry - 1) - cost_rt / 10_000.0


def _exit_target(bars, j, target, max_hold, cost_rt):
    entry = bars["open"][j]
    if entry <= 0:
        return None
    last = j
    for k in range(1, max_hold + 1):
        xi = min(j + k, len(bars["dates"]) - 1)
        r = bars["close"][xi] / entry - 1
        last = xi
        if r >= target or xi == len(bars["dates"]) - 1:
            return r - cost_rt / 10_000.0
    return (bars["close"][last] / entry - 1) - cost_rt / 10_000.0


VARIANTS = {
    "hold10": {"hypothesis_id": "kr_dart_buyback_hold10_v2_PIT",
               "exit": lambda bars, j, cost_rt: _exit_fixed(bars, j, HOLD_A, cost_rt),
               "pool_hold": HOLD_A, "note": f"HOLD={HOLD_A}일 고정청산"},
    "target5pct": {"hypothesis_id": "kr_dart_buyback_target5pct_v2_PIT",
                   "exit": lambda bars, j, cost_rt: _exit_target(bars, j, TARGET_B, MAX_HOLD_B, cost_rt),
                   "pool_hold": MAX_HOLD_B, "note": f"target={TARGET_B:.0%} 닿으면 즉시청산, 아니면 {MAX_HOLD_B}일차 청산"},
}


def _eval(events, series, exit_fn, cost_rt):
    out = []
    for e in events:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        j = _entry_idx(b, e["date"])
        if j is None:
            continue
        r = exit_fn(b, j, cost_rt)
        if r is not None:
            out.append((e["date"], r))
    return out


def _random_pool(series, pool_hold):
    pool = []
    for b in series.values():
        for j in range(len(b["dates"]) - pool_hold - 1):
            pool.append((b, j + 1))  # +1 = 진입일(다음날 시가) 인덱스
    return pool


def _run_variant(name, spec, events, series):
    print("\n" + "-" * 70)
    print(f"[{name}] {spec['note']}")
    pool = _random_pool(series, spec["pool_hold"])
    results = {}
    for cname, rt in COST_LEVELS.items():
        exit_fn = spec["exit"]
        be = _eval(events, series, lambda b, j, r=rt: exit_fn(b, j, r), rt)
        if not be:
            print("  매칭 0"); return None
        bnet = _st.mean([r for _, r in be])
        rng = _random.Random(SEED); rmeans = []
        for _ in range(N_RUNS):
            s = 0.0
            for _ in range(len(be)):
                b, j = pool[rng.randrange(len(pool))]
                r = exit_fn(b, j, rt)
                s += r if r is not None else 0.0
            rmeans.append(s / len(be))
        pv = empirical_p_value(bnet, rmeans)
        results[cname] = {"n": len(be), "net": round(bnet, 6), "pct": pv["percentile"], "p": pv["p_value"], "med": pv["random_median"]}
        print(f"  [{cname}] n={len(be)} net={bnet:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")

    be = _eval(events, series, lambda b, j, r=COST_LEVELS["base_20bps"]: spec["exit"](b, j, r), COST_LEVELS["base_20bps"])
    be.sort()
    mid = len(be) // 2
    fh = _st.mean([r for _, r in be[:mid]]); sh = _st.mean([r for _, r in be[mid:]])
    print(f"  walk-forward(base): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    base = results["base_20bps"]
    passed = (base["net"] > 0 and (base["pct"] or 0) >= 95 and (base["p"] or 1) < 0.05
              and fh > 0 and sh > 0 and results["stress_50bps"]["net"] > 0)
    verdict = ("WATCHLIST→PAPER 후보 — PIT 통과" if passed else
               "WEAK — random 80~95pct" if (base["net"] > 0 and (base["pct"] or 0) >= 80) else
               "REJECT — 매칭 random·비용 못 넘음")
    print(f"  VERDICT: {verdict}")

    log_experiment({"hypothesis_id": spec["hypothesis_id"], "status": "watchlist" if "WATCHLIST" in verdict else "rejected" if "REJECT" in verdict else "underpowered",
                    "variant": name, "trade_count": base["n"], "net_base": base["net"], "percentile": base["pct"], "p": base["p"],
                    "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "cost_stress": {k: v["net"] for k, v in results.items()},
                    "data_quality": "PIT + survivorship-free (KRX 스냅샷)", "verdict": verdict,
                    "note": f"익절variant({spec['note']}) — v1(HOLD20 고정) 동결 유지, 별도 사전등록"})
    return base["net"], verdict


def main():
    print("=" * 74 + "\nKR BUYBACK 청산룰 VARIANT 비교 (v1 동결, 별도 사전등록)\n" + "=" * 74)
    series = _load_all_series()
    events = load_events("buyback")
    print(f"buyback 이벤트 {len(events)}건 / KRX 시계열 {len(series)}종목")

    summary = {}
    for name, spec in VARIANTS.items():
        res = _run_variant(name, spec, events, series)
        if res:
            summary[name] = res

    print("\n" + "=" * 74)
    print("요약 (v1 base net = +0.0X 대는 ledger의 kr_dart_buyback_drift_v1_PIT 참조)")
    for name, (net, verdict) in summary.items():
        print(f"  {name:12} net={net:+.4f}  {verdict}")


if __name__ == "__main__":
    main()
