"""KR buyback 손절variant 비교(-5%/-10%/-15%, 사전등록 3종 동시 테스트) — v1 동결.
run_buyback_drawdown_dist.py 진단 근거로 임계치 3개 픽스, 사후 스윕 아님(FORBIDDEN list 준수).
오염 이벤트(run_buyback_split_audit.py 확인분) 3건 제외한 정제 데이터 기준.
룰: 보유기간 중 forward return이 stop 이하로 찍히면 즉시 청산, 아니면 HOLD일차 종가 청산.
익절 캡 없음(승자는 그대로 20일까지 감) — 손절만 건다.
실행: PYTHONPATH=. python3 research/run_buyback_stoploss_variants.py
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
from research.paper import buyback_config as CFG

HOLD = CFG.HOLD_DAYS
COST_LEVELS = {"base_20bps": 40.0, "stress_50bps": 100.0}
N_RUNS = 500
SEED = 42

CONTAMINATED = {("003920", "2024-10-23"), ("363260", "2026-08-10"), ("020180", "2026-07-20")}

STOP_CANDIDATES = {
    "stop15": {"stop": -0.15, "hypothesis_id": "kr_dart_buyback_stop15pct_v2_PIT"},
    "stop10": {"stop": -0.10, "hypothesis_id": "kr_dart_buyback_stop10pct_v2_PIT"},
    "stop5": {"stop": -0.05, "hypothesis_id": "kr_dart_buyback_stop5pct_v2_PIT"},
}


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


def _exit_stoploss(bars, j, stop, cost_rt):
    entry = bars["open"][j]
    if entry <= 0:
        return None
    last = j
    for k in range(1, HOLD + 1):
        xi = min(j + k, len(bars["dates"]) - 1)
        r = bars["close"][xi] / entry - 1
        last = xi
        if r <= stop or xi == len(bars["dates"]) - 1:
            return r - cost_rt / 10_000.0
    return (bars["close"][last] / entry - 1) - cost_rt / 10_000.0


def _eval(events, series, stop, cost_rt):
    out = []
    for e in events:
        if (e["stock_code"], e["date"]) in CONTAMINATED:
            continue
        b = series.get(e["stock_code"])
        if b is None:
            continue
        j = _entry_idx(b, e["date"])
        if j is None:
            continue
        r = _exit_stoploss(b, j, stop, cost_rt)
        if r is not None:
            out.append((e["date"], r))
    return out


def _random_pool(series):
    pool = []
    for b in series.values():
        for j in range(len(b["dates"]) - HOLD - 1):
            pool.append((b, j + 1))
    return pool


def _run_variant(name, spec, events, series, pool):
    stop = spec["stop"]
    print("\n" + "-" * 70)
    print(f"[{name}] stop={stop:.0%}, 아니면 {HOLD}일차 청산")
    results = {}
    for cname, rt in COST_LEVELS.items():
        be = _eval(events, series, stop, rt)
        if not be:
            print("  매칭 0"); return None
        bnet = _st.mean([r for _, r in be])
        rng = _random.Random(SEED); rmeans = []
        for _ in range(N_RUNS):
            s = 0.0
            for _ in range(len(be)):
                b, j = pool[rng.randrange(len(pool))]
                r = _exit_stoploss(b, j, stop, rt)
                s += r if r is not None else 0.0
            rmeans.append(s / len(be))
        pv = empirical_p_value(bnet, rmeans)
        results[cname] = {"n": len(be), "net": round(bnet, 6), "pct": pv["percentile"], "p": pv["p_value"], "med": pv["random_median"]}
        print(f"  [{cname}] n={len(be)} net={bnet:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")

    be = _eval(events, series, stop, COST_LEVELS["base_20bps"])
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
                    "data_quality": "PIT + survivorship-free (KRX 스냅샷), split-오염 3건 제외",
                    "verdict": verdict,
                    "note": f"손절variant(stop={stop:.0%}, 익절캡 없음) — v1 동결, 3종 사전등록 동시테스트 중 하나"})
    return base["net"], verdict


def main():
    print("=" * 74 + "\nKR BUYBACK 손절variant 비교 (-5%/-10%/-15%, 3종 사전등록, v1 동결)\n" + "=" * 74)
    series = _series()
    events = load_events("buyback")
    pool = _random_pool(series)
    print(f"buyback 이벤트 {len(events)}건(오염3건 제외 적용) / KRX 시계열 {len(series)}종목")

    summary = {}
    for name, spec in STOP_CANDIDATES.items():
        res = _run_variant(name, spec, events, series, pool)
        if res:
            summary[name] = res

    print("\n" + "=" * 74)
    print("요약 (v1 정제 net ≈ +0.0175, n=1975 — run_buyback_split_audit.py 참조)")
    for name, (net, verdict) in summary.items():
        print(f"  {name:12} net={net:+.4f}  {verdict}")


if __name__ == "__main__":
    main()
