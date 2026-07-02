"""KR Liquidity Wave Pullback v1 — 검증 실행 (RESEARCH_SANITY_CHECK_ONLY).

⚠️ survivorship/PIT/상장폐지/intraday/flow 없음 → sanity-check, 검증된 알파 아님.
질문: 임펄스+통제된 눌림+재돌파 이벤트가 매칭 random·비용 후 초과수익을 내는가?
실행: PYTHONPATH=. python3 research/run_kr_liquidity_wave.py [--limit N]
"""
from __future__ import annotations

import argparse
import random as _random
import statistics as _st

from research.data.kr_data import list_universe, filter_universe, list_delisted, load_ohlcv, load_stored, save_ohlcv
from research.strategies.kr_liquidity_wave import generate_trades, liquidity_bucket
from research.validation.baselines import empirical_p_value
from research.agents.experiment_registry import log_experiment

START, END = "2022-01-01", "2026-07-01"
COST_LEVELS = {"base_20bps": 40.0, "stress_50bps": 100.0, "severe_100bps": 200.0}  # 왕복 = 2×per-side
N_RUNS = 500
SEED = 42
MARCAP_MAX = 3e12  # small/mid 집중(초대형 제외)


def _bars(df) -> list[dict]:
    import datetime as dt
    out = []
    for idx, r in df.iterrows():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        out.append({"date": d, "open": float(r["Open"]), "high": float(r["High"]),
                    "low": float(r["Low"]), "close": float(r["Close"]), "tval": float(r["trading_value"])})
    return out


def _net(ret: float, roundtrip_bps: float) -> float:
    return ret - roundtrip_bps / 10_000.0


def load_universe(limit: int) -> list[dict]:
    uni = filter_universe(list_universe("KOSDAQ"))
    uni = [u for u in uni if u["marcap"] <= MARCAP_MAX]
    uni.sort(key=lambda u: -u["amount"])  # 유동성 큰 순
    return uni[:limit]


def _load_bars(code):
    df = load_stored(code)
    if len(df) == 0:
        try:
            df = load_ohlcv(code, START, END)
            if len(df):
                save_ohlcv(code, df)
        except Exception:
            return None
    return df if len(df) >= 60 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--delisted", type=int, default=200, help="상장폐지 종목 포함 수(survivorship 통제)")
    args = ap.parse_args()

    print("=" * 74)
    print("KR LIQUIDITY WAVE PULLBACK v1 — survivorship 통제(상장폐지 포함)")
    print("(PIT universe/intraday/flow 여전히 없음 → sanity 개선판)")
    print("=" * 74)

    survivors = load_universe(args.limit)
    delisted = list_delisted("KOSDAQ", "2022-01-01")[: args.delisted]
    print(f"survivor {len(survivors)} + delisted {len(delisted)} 종목")

    all_trades, pool = [], []
    src_counts = {"survivor": 0, "delisted": 0}

    # survivor (스냅샷 amount로 bucket)
    for j, u in enumerate(survivors, 1):
        df = _load_bars(u["code"])
        if df is None:
            continue
        bars = _bars(df)
        bucket = liquidity_bucket(u["amount"])
        for t in generate_trades(bars):
            t["bucket"] = bucket; t["source"] = "survivor"; all_trades.append(t)
            src_counts["survivor"] += 1
        n = len(bars)
        for i in range(20, n - 11):
            pool.append((bucket, bars, i))
        if j % 50 == 0:
            print(f"  survivor {j}/{len(survivors)}, 누적 {len(all_trades)}")

    # delisted (역사적 유동성으로 게이트+bucket)
    for j, u in enumerate(delisted, 1):
        df = _load_bars(u["code"])
        if df is None:
            continue
        bars = _bars(df)
        tvs = [b["tval"] for b in bars]; pxs = [b["close"] for b in bars]
        if len(tvs) < 20:
            continue
        # 이벤트윈도우 유동성: 20일 롤링평균 최대치(펌프 시점에 유동성 있었으면 자격)
        roll_max = max(_st.mean(tvs[i - 20:i]) for i in range(20, len(tvs) + 1))
        if roll_max < 3e9 or (pxs and max(pxs) < 1000):
            continue
        bucket = liquidity_bucket(roll_max)
        for t in generate_trades(bars):
            t["bucket"] = bucket; t["source"] = "delisted"; all_trades.append(t)
            src_counts["delisted"] += 1
        n = len(bars)
        for i in range(20, n - 11):
            pool.append((bucket, bars, i))
        if j % 50 == 0:
            print(f"  delisted {j}/{len(delisted)}, 누적 {len(all_trades)}")

    print(f"\n트레이드 소스: survivor {src_counts['survivor']} / delisted {src_counts['delisted']}")
    K = len(all_trades)
    if K == 0:
        print("트레이드 0 — 이벤트 없음/데이터 부족")
        return
    holds = [t["exit_idx"] - t["entry_idx"] for t in all_trades]
    mean_hold = max(1, round(_st.mean(holds)))
    gross_rets = [t["ret"] for t in all_trades]

    print(f"\n전략 트레이드: {K}개 | 평균보유 {mean_hold}일 | gross 평균수익 {_st.mean(gross_rets):+.4f} "
          f"| 승률 {sum(1 for r in gross_rets if r>0)/K:.3f}")

    # 비용 스트레스 + matched random
    print("\n비용 스트레스 & matched random (같은 bucket·같은 보유·같은 비용):")
    results = {}
    # bucket별 pool 인덱스
    by_bucket = {}
    for idx, (b, bars, i) in enumerate(pool):
        by_bucket.setdefault(b, []).append(idx)
    trade_buckets = [t["bucket"] for t in all_trades]

    for name, rt_bps in COST_LEVELS.items():
        net_strat = _st.mean([_net(r, rt_bps) for r in gross_rets])
        rng = _random.Random(SEED)
        rand_means = []
        for _ in range(N_RUNS):
            rr = []
            for b in trade_buckets:
                cands = by_bucket.get(b) or [idx for idx in range(len(pool))]
                pj = pool[rng.choice(cands)]
                _, bars, i = pj
                ei = i + 1
                xi = min(ei + mean_hold, len(bars) - 1)
                entry, exit_ = bars[ei]["open"], bars[xi]["close"]
                rr.append(_net(exit_ / entry - 1, rt_bps) if entry > 0 else 0.0)
            rand_means.append(_st.mean(rr))
        pv = empirical_p_value(net_strat, rand_means)
        results[name] = {"net_mean": round(net_strat, 6), "percentile": pv["percentile"],
                         "p": pv["p_value"], "rand_median": pv["random_median"]}
        print(f"  {name:14} net평균={net_strat:+.4f}  vs random pct={pv['percentile']} p={pv['p_value']} "
              f"(rand_med={pv['random_median']:+.4f})")

    # walk-forward (이벤트일 기준 2분할)
    all_trades.sort(key=lambda t: t["event_date"])
    mid = K // 2
    fh = _st.mean([_net(t["ret"], COST_LEVELS["base_20bps"]) for t in all_trades[:mid]])
    sh = _st.mean([_net(t["ret"], COST_LEVELS["base_20bps"]) for t in all_trades[mid:]])
    print(f"\nwalk-forward(base cost): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    # survivor vs delisted 분해 (survivorship 통제 효과)
    rt = COST_LEVELS["base_20bps"]
    surv = [_net(t["ret"], rt) for t in all_trades if t.get("source") == "survivor"]
    deli = [_net(t["ret"], rt) for t in all_trades if t.get("source") == "delisted"]
    print(f"소스 분해(net base): survivor {_st.mean(surv):+.4f}(n={len(surv)}) / "
          f"delisted {(_st.mean(deli) if deli else 0):+.4f}(n={len(deli)})")

    # 판정 (sanity 기준)
    base = results["base_20bps"]
    powered = K >= 50
    passed = (base["net_mean"] > 0 and (base["percentile"] or 0) >= 95
              and (base["p"] or 1) < 0.05 and fh > 0 and sh > 0
              and results["stress_50bps"]["net_mean"] > 0)
    if not powered:
        verdict = "UNDERPOWERED — 트레이드 부족(sanity)"
    elif passed:
        verdict = "WATCHLIST(sanity only) — 매칭random·비용후 통과하나 survivorship 미제어"
    elif base["net_mean"] > 0 and (base["percentile"] or 0) >= 80:
        verdict = "WEAK — random 80~95pct"
    else:
        verdict = "REJECT — 매칭 random·비용 넘지 못함"
    print(f"\nVERDICT: {verdict}")
    print("⚠️ RESEARCH_SANITY_CHECK_ONLY (검증된 알파 아님, 라이브 권고 아님)")

    log_experiment({"hypothesis_id": "kr_liquidity_wave_pullback_v1_eventwin", "status": "rejected" if "REJECT" in verdict else "watchlist" if "WATCHLIST" in verdict else "underpowered",
                    "trade_count": K, "gross_mean": round(_st.mean(gross_rets), 6),
                    "net_base": base["net_mean"], "percentile_base": base["percentile"], "p_base": base["p"],
                    "cost_stress": {k: v["net_mean"] for k, v in results.items()},
                    "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "survivor_net": round(_st.mean(surv), 6) if surv else None,
                    "delisted_net": round(_st.mean(deli), 6) if deli else None,
                    "delisted_trades": len(deli),
                    "data_quality": "RESEARCH_SANITY_CHECK_ONLY (survivorship 통제, PIT/flow 여전히 없음)",
                    "verdict": verdict,
                    "note": "상장폐지 포함(survivorship 통제), 거래대금=Close*Vol 프록시, PIT universe 아님, 고정파라미터"})


if __name__ == "__main__":
    main()
