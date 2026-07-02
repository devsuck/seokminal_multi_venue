"""KR 공시 이벤트 스터디 — 자기주식취득(buyback, 강세) 포워드 수익 검증.

질문: 공시일 다음날 진입, N일 보유 시 매칭 random·비용 후 초과수익이 있는가?
lookahead 방지(공시일 기준 다음날 진입). 대조: rights_issue(유상증자, 약세)는 낮아야.
실행: PYTHONPATH=. python3 research/run_kr_dart_event_study.py
"""
from __future__ import annotations

import bisect
import random as _random
import statistics as _st

from research.data.kr_data import load_stored, load_ohlcv, save_ohlcv
from research.data.kr_dart_events import load_events
from research.validation.baselines import empirical_p_value
from research.agents.experiment_registry import log_experiment

START, END = "2022-01-01", "2026-07-01"
HOLD = 20          # 보유 거래일(이벤트 드리프트 ~1개월)
COST_LEVELS = {"base_20bps": 40.0, "stress_50bps": 100.0}  # 왕복
N_RUNS = 500
SEED = 42


def _stock_bars(code: str):
    df = load_stored(code)
    if len(df) == 0:
        try:
            df = load_ohlcv(code, START, END)
            if len(df):
                save_ohlcv(code, df)
        except Exception:
            return None
    if len(df) < HOLD + 5:
        return None
    dates = [(idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)) for idx in df.index]
    return {"dates": dates, "open": df["Open"].astype(float).tolist(), "close": df["Close"].astype(float).tolist()}


def _fwd_return(bars, event_date: str):
    """공시일 다음 거래일 시가 진입 → HOLD일 후 종가. (없으면 None)."""
    j = bisect.bisect_right(bars["dates"], event_date)  # event_date 초과 첫 인덱스 = 다음 거래일
    if j >= len(bars["dates"]):
        return None
    entry = bars["open"][j]
    xi = min(j + HOLD, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return bars["close"][xi] / entry - 1


def _net(r, rt):
    return r - rt / 10_000.0


def evaluate_event(event: str, cache: dict, cost_rt: float):
    events = load_events(event)
    rets = []
    for e in events:
        code = e["stock_code"]
        if code not in cache:
            cache[code] = _stock_bars(code)
        bars = cache[code]
        if bars is None:
            continue
        r = _fwd_return(bars, e["date"])
        if r is not None:
            rets.append((e["date"], _net(r, cost_rt)))
    return rets


def matched_random(cache: dict, n: int, cost_rt: float):
    """같은 종목 pool·같은 보유·같은 비용, 랜덤 (종목,날짜) → net 분포."""
    pool = []
    for code, bars in cache.items():
        if bars is None:
            continue
        for j in range(len(bars["dates"]) - HOLD - 1):
            pool.append((bars, j))
    if not pool or n <= 0:
        return [0.0] * N_RUNS
    rng = _random.Random(SEED)
    out = []
    for _ in range(N_RUNS):
        s = 0.0
        for _ in range(n):
            bars, j = pool[rng.randrange(len(pool))]
            entry = bars["open"][j + 1]
            xi = min(j + 1 + HOLD, len(bars["dates"]) - 1)
            s += _net(bars["close"][xi] / entry - 1, cost_rt) if entry > 0 else 0.0
        out.append(s / n)
    return out


def main():
    print("=" * 74)
    print("KR DART EVENT STUDY — 자기주식취득(buyback) 포워드 수익 (RESEARCH)")
    print(f"공시 다음날 진입 · {HOLD}일 보유 · 매칭 random · 비용 스트레스")
    print("=" * 74)

    cache: dict = {}
    results = {}
    for name, rt in COST_LEVELS.items():
        bb = evaluate_event("buyback", cache, rt)
        if not bb:
            print("buyback 이벤트/데이터 0"); return
        bb_net = _st.mean([r for _, r in bb])
        rnd = matched_random(cache, len(bb), rt)
        pv = empirical_p_value(bb_net, rnd)
        # rights 대조
        ri = evaluate_event("rights_issue", cache, rt)
        ri_net = _st.mean([r for _, r in ri]) if ri else None
        results[name] = {"n": len(bb), "buyback_net": round(bb_net, 6), "percentile": pv["percentile"],
                         "p": pv["p_value"], "rand_med": pv["random_median"],
                         "rights_net": round(ri_net, 6) if ri_net is not None else None, "rights_n": len(ri)}
        print(f"\n[{name}] buyback n={len(bb)} net={bb_net:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} "
              f"(rand_med={pv['random_median']:+.4f})")
        print(f"  대조 rights_issue(약세) n={len(ri)} net={ri_net:+.4f}" if ri_net is not None else "  rights 없음")

    # walk-forward (base cost, 이벤트일 기준)
    bb = evaluate_event("buyback", cache, COST_LEVELS["base_20bps"])
    bb.sort()
    mid = len(bb) // 2
    fh = _st.mean([r for _, r in bb[:mid]]); sh = _st.mean([r for _, r in bb[mid:]])
    print(f"\nwalk-forward(base): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    base = results["base_20bps"]
    powered = base["n"] >= 50
    passed = (base["buyback_net"] > 0 and (base["percentile"] or 0) >= 95 and (base["p"] or 1) < 0.05
              and fh > 0 and sh > 0 and results["stress_50bps"]["buyback_net"] > 0)
    if not powered:
        verdict = "UNDERPOWERED"
    elif passed:
        verdict = "WATCHLIST 후보 — 매칭random·비용후 통과(PIT/생존편향 검토 필요)"
    elif base["buyback_net"] > 0 and (base["percentile"] or 0) >= 80:
        verdict = "WEAK — random 80~95pct"
    else:
        verdict = "REJECT — 매칭 random·비용 못 넘음"
    print(f"\nVERDICT: {verdict}")

    log_experiment({"hypothesis_id": "kr_dart_buyback_drift_v1", "status": "rejected" if "REJECT" in verdict else "watchlist" if "WATCHLIST" in verdict else "underpowered",
                    "event": "buyback(자기주식취득)", "hold_days": HOLD, "trade_count": base["n"],
                    "buyback_net_base": base["buyback_net"], "percentile": base["percentile"], "p": base["p"],
                    "rights_net_base": base["rights_net"], "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "verdict": verdict, "note": "OpenDART 공시 이벤트, 공시다음날 진입, 매칭random, 고정파라미터. PIT/생존편향 미검토"})


if __name__ == "__main__":
    main()
