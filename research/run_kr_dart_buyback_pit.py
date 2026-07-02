"""KR 자사주취득(buyback) 이벤트 스터디 — PIT/survivorship-free (KRX 공식 스냅샷).

FDR 버전(생존편향)과 달리 KRX 날짜별 스냅샷 재구성 시계열 사용:
폐지종목은 활동기간에만 존재 → 자사주 후 폭락·상폐도 포워드 수익에 반영(편향 제거).
공시 다음날 시가 진입 · N일 보유 · 매칭 random · 비용 스트레스 · 유상증자 대조.
실행: PYTHONPATH=. python3 research/run_kr_dart_buyback_pit.py
"""
from __future__ import annotations

import bisect
import random as _random
import statistics as _st

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events
from research.validation.baselines import empirical_p_value
from research.agents.experiment_registry import log_experiment
import glob
import os

HOLD = 20
COST_LEVELS = {"base_20bps": 40.0, "stress_50bps": 100.0}
N_RUNS = 500
SEED = 42


def _load_all_series() -> dict:
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _fwd(bars: dict, event_date: str, cost_rt: float):
    """공시 다음날 시가 진입 → HOLD일 후 종가(폐지면 마지막 종가). net 반환."""
    j = bisect.bisect_right(bars["dates"], event_date)  # 다음 거래일
    if j >= len(bars["dates"]):
        return None
    entry = bars["open"][j]
    xi = min(j + HOLD, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return (bars["close"][xi] / entry - 1) - cost_rt / 10_000.0


def _eval(events, series, cost_rt):
    out = []
    for e in events:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        r = _fwd(b, e["date"], cost_rt)
        if r is not None:
            out.append((e["date"], r))
    return out


def _random_pool(series):
    pool = []
    for b in series.values():
        for j in range(len(b["dates"]) - HOLD - 1):
            pool.append((b, j))
    return pool


def main():
    print("=" * 74)
    print("KR 자사주(buyback) 이벤트 스터디 — PIT/survivorship-free (KRX 공식)")
    print("=" * 74)
    series = _load_all_series()
    n_kospi = sum(1 for _ in glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")))
    print(f"KRX 시계열: {len(series)}종목 (KOSPI 스냅 {n_kospi}일 {'포함' if n_kospi else '미포함'})")

    bb = load_events("buyback")
    ri = load_events("rights_issue")
    pool = _random_pool(series)
    print(f"buyback 이벤트 {len(bb)} / rights {len(ri)} | random pool {len(pool)}")

    results = {}
    by_bucket = None
    for name, rt in COST_LEVELS.items():
        be = _eval(bb, series, rt)
        if not be:
            print("buyback 매칭 0 (KRX 범위 밖?)"); return
        bnet = _st.mean([r for _, r in be])
        rng = _random.Random(SEED); rmeans = []
        for _ in range(N_RUNS):
            s = 0.0
            for _ in range(len(be)):
                b, j = pool[rng.randrange(len(pool))]
                e0 = b["open"][j + 1]; xi = min(j + 1 + HOLD, len(b["dates"]) - 1)
                s += ((b["close"][xi] / e0 - 1) - rt / 10_000.0) if e0 > 0 else 0.0
            rmeans.append(s / len(be))
        pv = empirical_p_value(bnet, rmeans)
        re = _eval(ri, series, rt); rnet = _st.mean([r for _, r in re]) if re else None
        results[name] = {"n": len(be), "net": round(bnet, 6), "pct": pv["percentile"], "p": pv["p_value"],
                         "med": pv["random_median"], "rights_net": round(rnet, 6) if rnet is not None else None, "rn": len(re)}
        print(f"\n[{name}] buyback n={len(be)} net={bnet:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")
        print(f"  대조 rights(약세) n={len(re)} net={rnet:+.4f}" if rnet is not None else "  rights 0")

    be = _eval(bb, series, COST_LEVELS["base_20bps"]); be.sort()
    mid = len(be) // 2
    fh = _st.mean([r for _, r in be[:mid]]); sh = _st.mean([r for _, r in be[mid:]])
    print(f"\nwalk-forward(base): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    base = results["base_20bps"]
    passed = (base["net"] > 0 and (base["pct"] or 0) >= 95 and (base["p"] or 1) < 0.05
              and fh > 0 and sh > 0 and results["stress_50bps"]["net"] > 0)
    verdict = ("WATCHLIST→PAPER 후보 — PIT/survivorship-free 통과" if passed else
               "WEAK — random 80~95pct" if (base["net"] > 0 and (base["pct"] or 0) >= 80) else
               "REJECT — 매칭 random·비용 못 넘음" if base["net"] <= 0 or (base["pct"] or 0) < 80 else "INCONCLUSIVE")
    print(f"\nVERDICT: {verdict}")
    print("데이터: PIT + survivorship-free (KRX 스냅). intraday 미포함")

    log_experiment({"hypothesis_id": "kr_dart_buyback_drift_v1_PIT", "status": "watchlist" if "WATCHLIST" in verdict or "PAPER" in verdict else "rejected" if "REJECT" in verdict else "underpowered",
                    "hold_days": HOLD, "trade_count": base["n"], "net_base": base["net"], "percentile": base["pct"], "p": base["p"],
                    "rights_net": base["rights_net"], "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "cost_stress": {k: v["net"] for k, v in results.items()},
                    "data_quality": "PIT + survivorship-free (KRX 스냅샷)", "verdict": verdict,
                    "note": "KRX 시계열로 포워드수익, 폐지종목 자동반영, 다음날진입, 고정파라미터"})


if __name__ == "__main__":
    main()
