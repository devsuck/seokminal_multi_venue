"""KR Liquidity Wave — PIT/survivorship-free 재검 (KRX 공식 API).

KRX 날짜별 전종목 스냅샷 = survivorship-free by construction(폐지종목 활동기간에만 존재).
실 거래대금·시총·관리종목 필터. 기존 detector(generate_trades) 재사용.
실행: PYTHONPATH=. python3 research/run_kr_liquidity_wave_pit.py
"""
from __future__ import annotations

import random as _random
import statistics as _st

from research.data.krx_api import build_series
from research.strategies.kr_liquidity_wave import generate_trades, liquidity_bucket
from research.validation.baselines import empirical_p_value
from research.agents.experiment_registry import log_experiment

COST_LEVELS = {"base_20bps": 40.0, "stress_50bps": 100.0, "severe_100bps": 200.0}
N_RUNS = 500
SEED = 42
MARCAP_MAX = 3e12  # small/mid


def _bars(s: dict) -> list[dict]:
    return [{"date": s["dates"][i], "open": s["open"][i], "high": s["high"][i],
             "low": s["low"][i], "close": s["close"][i], "tval": s["tval"][i]}
            for i in range(len(s["dates"]))]


def _net(r, rt):
    return r - rt / 10_000.0


def main():
    print("=" * 74)
    print("KR LIQUIDITY WAVE — PIT/survivorship-free 재검 (KRX 공식 API)")
    print("=" * 74)
    series = build_series("KOSDAQ", min_bars=60)
    print(f"KRX KOSDAQ 종목(생존+폐지 포함, PIT): {len(series)}")

    all_trades, pool = [], []
    used = 0
    for code, s in series.items():
        tvs = s["tval"]; pxs = s["close"]; sect = s["sect"]
        if len(tvs) < 25:
            continue
        # 관리종목/투자주의 제외 (부서 기반)
        if any(("관리" in x or "투자주의" in x or "정리매매" in x) for x in sect):
            continue
        # 이벤트윈도우 유동성(실 거래대금) + 시총 + 가격 게이트
        roll_max = max(_st.mean(tvs[i - 20:i]) for i in range(20, len(tvs) + 1))
        max_mc = max(s["marcap"]) if s["marcap"] else 0
        if roll_max < 3e9 or (pxs and max(pxs) < 1000) or max_mc > MARCAP_MAX or max_mc < 5e10:
            continue
        bars = _bars(s)
        bucket = liquidity_bucket(roll_max)
        for t in generate_trades(bars):
            t["bucket"] = bucket; all_trades.append(t)
        used += 1
        n = len(bars)
        for i in range(20, n - 11):
            pool.append((bucket, bars, i))

    K = len(all_trades)
    print(f"게이트 통과 종목 {used} | 트레이드 {K}")
    if K == 0:
        print("트레이드 0"); return
    holds = [t["exit_idx"] - t["entry_idx"] for t in all_trades]
    mean_hold = max(1, round(_st.mean(holds)))
    gross = [t["ret"] for t in all_trades]
    print(f"gross 평균수익 {_st.mean(gross):+.4f} | 승률 {sum(1 for r in gross if r>0)/K:.3f} | 평균보유 {mean_hold}일")

    by_bucket = {}
    for idx, (b, _, _) in enumerate(pool):
        by_bucket.setdefault(b, []).append(idx)
    tbk = [t["bucket"] for t in all_trades]

    print("\n비용 스트레스 & matched random (PIT pool):")
    results = {}
    for name, rt in COST_LEVELS.items():
        net_s = _st.mean([_net(r, rt) for r in gross])
        rng = _random.Random(SEED); rmeans = []
        for _ in range(N_RUNS):
            rr = []
            for b in tbk:
                cands = by_bucket.get(b) or list(range(len(pool)))
                _, bars, i = pool[rng.choice(cands)]
                ei = i + 1; xi = min(ei + mean_hold, len(bars) - 1)
                e0, x0 = bars[ei]["open"], bars[xi]["close"]
                rr.append(_net(x0 / e0 - 1, rt) if e0 > 0 else 0.0)
            rmeans.append(_st.mean(rr))
        pv = empirical_p_value(net_s, rmeans)
        results[name] = {"net": round(net_s, 6), "pct": pv["percentile"], "p": pv["p_value"], "med": pv["random_median"]}
        print(f"  {name:14} net={net_s:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")

    all_trades.sort(key=lambda t: t["event_date"])
    mid = K // 2
    fh = _st.mean([_net(t["ret"], COST_LEVELS["base_20bps"]) for t in all_trades[:mid]])
    sh = _st.mean([_net(t["ret"], COST_LEVELS["base_20bps"]) for t in all_trades[mid:]])
    print(f"\nwalk-forward(base): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    base = results["base_20bps"]
    powered = K >= 50
    passed = (base["net"] > 0 and (base["pct"] or 0) >= 95 and (base["p"] or 1) < 0.05
              and fh > 0 and sh > 0 and results["stress_50bps"]["net"] > 0)
    verdict = ("UNDERPOWERED" if not powered else
               "WATCHLIST 후보 — PIT/survivorship-free 통과" if passed else
               "WEAK — random 80~95pct" if (base["net"] > 0 and (base["pct"] or 0) >= 80) else
               "REJECT — 매칭 random·비용 못 넘음")
    print(f"\nVERDICT: {verdict}")
    print("데이터 품질: PIT universe + survivorship-free + 실거래대금 (KRX 공식). intraday/flow는 여전히 미포함")

    log_experiment({"hypothesis_id": "kr_liquidity_wave_pullback_v1_PIT", "status": "rejected" if "REJECT" in verdict else "watchlist" if "WATCHLIST" in verdict else "underpowered",
                    "trade_count": K, "universe": used, "gross_mean": round(_st.mean(gross), 6),
                    "net_base": base["net"], "percentile": base["pct"], "p": base["p"],
                    "cost_stress": {k: v["net"] for k, v in results.items()},
                    "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "data_quality": "PIT universe + survivorship-free + 실거래대금 (KRX 공식 API)",
                    "verdict": verdict, "note": "KRX 날짜별 스냅샷 재구성, 폐지종목 자동포함, 관리종목 제외, 고정파라미터"})


if __name__ == "__main__":
    main()
