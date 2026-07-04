"""KR CB/BW 조기상환(오버행 해소) 이벤트 스터디 — PIT/survivorship-free (KRX 공식 스냅샷).

가설: CB 발행결정 = 희석/리픽싱 악재 → 발행 익일부터 음의 드리프트(회피 연구, 억지 숏 아님).
buyback와 같은 자본구조 이벤트 family지만 방향 반대(공급 증가). 폐지종목 자동반영(편향 제거).
공시 다음날 시가 진입 · N일 보유 · 매칭 random · 비용 스트레스 · buyback(호재) 대조.
실행: PYTHONPATH=. python3 research/run_cb_issuance_pit.py
"""
from __future__ import annotations

import bisect
import glob
import os
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.kr_dart_events import load_events
from research.data.krx_api import build_series, market_dir
from research.validation.baselines import empirical_p_value

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
    j = bisect.bisect_right(bars["dates"], event_date)
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
    print("KR CB/BW 조기상환(오버행 해소) 이벤트 스터디 — PIT/survivorship-free (KRX 공식)")
    print("=" * 74)
    cb = load_events("cb_release")
    if not cb:
        print("cb_release 이벤트 없음 — 먼저 pull 필요: "
              "python3 -c \"from research.data.kr_dart_events import pull_events,save_events; "
              "save_events('cb_release', pull_events('cb_release', years=6.5))\"")
        return

    series = _load_all_series()
    n_kospi = sum(1 for _ in glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")))
    print(f"KRX 시계열: {len(series)}종목 (KOSPI 스냅 {n_kospi}일)")

    bb = load_events("buyback")   # 호재 대조
    pool = _random_pool(series)
    print(f"cb_release 이벤트 {len(cb)} / buyback(대조) {len(bb)} | random pool {len(pool)}")

    results = {}
    for name, rt in COST_LEVELS.items():
        ce = _eval(cb, series, rt)
        if not ce:
            print("cb_release 매칭 0 (KRX 범위 밖?)"); return
        cnet = _st.mean([r for _, r in ce])
        rng = _random.Random(SEED); rmeans = []
        for _ in range(N_RUNS):
            s = 0.0
            for _ in range(len(ce)):
                b, j = pool[rng.randrange(len(pool))]
                e0 = b["open"][j + 1]; xi = min(j + 1 + HOLD, len(b["dates"]) - 1)
                s += ((b["close"][xi] / e0 - 1) - rt / 10_000.0) if e0 > 0 else 0.0
            rmeans.append(s / len(ce))
        pv = empirical_p_value(cnet, rmeans)
        be = _eval(bb, series, rt); bnet = _st.mean([r for _, r in be]) if be else None
        results[name] = {"n": len(ce), "net": round(cnet, 6), "pct": pv["percentile"], "p": pv["p_value"],
                         "med": pv["random_median"], "buyback_net": round(bnet, 6) if bnet is not None else None}
        print(f"\n[{name}] cb_release n={len(ce)} net={cnet:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")
        print(f"  대조 buyback(호재) net={bnet:+.4f}" if bnet is not None else "  buyback 0")

    # 음의 드리프트 판정: net이 random 하위(음의 엣지)인가?
    ce = _eval(cb, series, COST_LEVELS["base_20bps"]); ce.sort()
    mid = len(ce) // 2
    fh = _st.mean([r for _, r in ce[:mid]]); sh = _st.mean([r for _, r in ce[mid:]])
    print(f"\nwalk-forward(base): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    base = results["base_20bps"]
    pct = base["pct"] if base["pct"] is not None else 50.0
    # 오버행 해소(조기상환) = 호재 가설: random 상위(양드리프트)인가?
    pos_edge = base["net"] > 0 and pct >= 95 and (base["p"] or 1) < 0.05 and fh > 0 and sh > 0
    verdict = ("EDGE 후보 — 조기상환 후 양드리프트(오버행 해소 호재)" if pos_edge else
               "WEAK — random 80~95pct" if base["net"] > 0 and pct >= 80 else
               "REJECT — 조기상환 드리프트 없음")
    print(f"\nVERDICT: {verdict}")
    print("데이터: PIT + survivorship-free (KRX 스냅). 연구전용, live 매매 아님.")

    log_experiment({"hypothesis_id": "kr_cb_release_drift_v1_PIT",
                    "status": "candidate" if pos_edge else "weak" if (base["net"] > 0 and pct >= 80) else "rejected",
                    "hold_days": HOLD, "trade_count": base["n"], "net_base": base["net"],
                    "percentile": base["pct"], "p": base["p"], "buyback_ref_net": base["buyback_net"],
                    "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "cost_stress": {k: v["net"] for k, v in results.items()},
                    "data_quality": "PIT + survivorship-free (KRX 스냅샷)", "verdict": verdict,
                    "note": "CB발행 익일진입 20일보유 음드리프트 연구(회피용, 숏 아님). 고정파라미터"})


if __name__ == "__main__":
    main()
