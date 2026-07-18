"""IB 선물(NQ/MNQ/GC) 15분봉 OHLCV 기반 바-레벨 오더플로우 프리미티브 조합 스윕.

⚠️ tick 단위 buy/sell 방향 데이터 없음(footprint/absorption/cvd/large_trade/tape_vwap는
IB 틱 컬렉터 미가동으로 원천 데이터 부재) — 이 모듈은 순수 OHLCV(o,h,l,c,volume)만으로
계산 가능한 3개 프리미티브만 다룬다: vwap_window(롤링 VWAP 크로스), trend_15m
(market_structure), key_level_15m(스윙 근접). 계산 로직은 orderflow_context_gate.py의
build_trend_filter/build_key_level_filter를 그대로 재사용(신규 지표 발명 없음).

BTC.HL 8-프리미티브 255콤보 스윕(run_orderflow_full_sweep_btc.py)과 표본 크기·검정력이
다르다 — 같은 급으로 비교하지 말 것.

⚠️ DORMANT 확인용 스크립트. 실집행 근거 아님.
"""
from __future__ import annotations

from itertools import combinations

from research.hypotheses.orderflow_context_gate import build_key_level_filter, build_trend_filter
from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.cost_model import ib_futures_effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics

# 원본 60s버킷 240개(=4시간) 롤링 윈도우를 15분봉 기준으로 환산 — 16*15m=4시간. 고정, 최적화 금지.
FUTURES_VWAP_WINDOW_BARS = 16

FUTURES_MULTIPLIER = {"NQ": 20.0, "MNQ": 2.0, "GC": 100.0}  # $/포인트 (GC: 100트로이온스)

PRIMITIVE_NAMES = ("vwap_window", "trend_15m", "key_level_15m")


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def build_primitive_signals(bars: dict) -> dict:
    """bars: load_ohlc_lists() 반환 형식({ts, open, high, low, close, volume})."""
    closes, vols = bars["close"], bars["volume"]
    n = len(closes)

    vw_sig: list[str] = []
    vw_elig: list[int] = []
    for i in range(n):
        start = max(0, i - FUTURES_VWAP_WINDOW_BARS + 1)
        wc, wv = closes[start:i + 1], vols[start:i + 1]
        total_vol = sum(wv)
        sig = "HOLD"
        if total_vol > 0:
            vw_elig.append(i)
            vwap = sum(p * v for p, v in zip(wc, wv)) / total_vol
            if closes[i] > vwap:
                sig = "BUY"
            elif closes[i] < vwap:
                sig = "SELL"
        vw_sig.append(sig)

    ohlc_15m = [
        {"bucket_ts": ts, "o": o, "h": h, "l": l, "c": c}
        for ts, o, h, l, c in zip(bars["ts"], bars["open"], bars["high"], bars["low"], closes)
    ]
    trend_sig = build_trend_filter(ohlc_15m)
    keylvl_sig = build_key_level_filter(ohlc_15m)
    all_elig = list(range(n))

    return {
        "closes": closes,
        "primitives": {
            "vwap_window": {"signals": vw_sig, "eligible": vw_elig},
            "trend_15m": {"signals": trend_sig, "eligible": all_elig},
            "key_level_15m": {"signals": keylvl_sig, "eligible": all_elig},
        },
    }


def combine_and_n(sig_elig_pairs: list[tuple[list[str], list[int]]], n: int) -> dict:
    elig_sets = [set(elig) for _, elig in sig_elig_pairs]
    common = set.intersection(*elig_sets) if elig_sets else set()
    signals: list[str] = []
    for i in range(n):
        sig = "HOLD"
        if i in common:
            dirs = {sigs[i] for sigs, _ in sig_elig_pairs}
            if len(dirs) == 1 and "HOLD" not in dirs:
                sig = next(iter(dirs))
        signals.append(sig)
    return {"signals": signals, "eligible": sorted(common)}


def _run_combo(symbol: str, combo_name: str, closes: list[float], combo: dict,
               n_runs: int, seed: int, cost_bps: float, multiplier: float) -> dict | None:
    signals, eligible = combo["signals"], combo["eligible"]
    if len(closes) < 10:
        return None
    trades = simulate_long_short(closes, signals, trade_size=multiplier, cost_bps=cost_bps)
    strat = trade_metrics(trades)
    if strat["num_trades"] == 0:
        return {"symbol": symbol, "combo": combo_name, "strategy": strat,
                "random": {"p_value": None, "percentile": None}, "eligible_count": len(eligible)}
    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=multiplier, cost_bps=cost_bps,
        eligible_indices=eligible, n_runs=n_runs, seed=seed,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)
    return {"symbol": symbol, "combo": combo_name, "strategy": strat,
            "random": pval, "eligible_count": len(eligible)}


def run_matrix(symbol: str, bars: dict, n_runs: int = 500, seed: int = 42) -> dict:
    """3개 프리미티브 전조합: 단일 3 + 페어와이즈AND 3 + 3-way AND 1 = 7개."""
    closes = bars["close"]
    n = len(closes)
    if n < 10:
        return {"symbol": symbol, "blocked": True, "reason": f"{n}봉뿐 — 최소 표본 미달"}

    data = build_primitive_signals(bars)
    prim = data["primitives"]
    multiplier = FUTURES_MULTIPLIER[symbol]
    notional = _median(closes) * multiplier
    cost_bps = ib_futures_effective_cost_bps(symbol, notional)

    results: list[dict] = []
    for name in PRIMITIVE_NAMES:
        p = prim[name]
        r = _run_combo(symbol, name, closes, p, n_runs, seed, cost_bps, multiplier)
        if r:
            results.append(r)

    for name_a, name_b in combinations(PRIMITIVE_NAMES, 2):
        a, b = prim[name_a], prim[name_b]
        combo = combine_and_n([(a["signals"], a["eligible"]), (b["signals"], b["eligible"])], n)
        r = _run_combo(symbol, f"{name_a}+{name_b}", closes, combo, n_runs, seed, cost_bps, multiplier)
        if r:
            results.append(r)

    all3 = combine_and_n([(prim[name]["signals"], prim[name]["eligible"]) for name in PRIMITIVE_NAMES], n)
    r = _run_combo(symbol, "+".join(PRIMITIVE_NAMES), closes, all3, n_runs, seed, cost_bps, multiplier)
    if r:
        results.append(r)

    return {"symbol": symbol, "blocked": False, "n_bars": n, "results": results}
