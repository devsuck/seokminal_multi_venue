"""오더플로우 프리미티브 8개를 하나의 60s bar 피처행렬 위에서 조합 — 페어와이즈
합의(AND) + killzone 게이팅. 지금까지 각자 다른 구현(footprint_delta float bucket_ts,
absorption.py/tape_vwap.py의 int 버킷 인덱스)이 따로 놀아서 조합하려면 버킷 정렬을
매번 검증해야 했음 — 여기선 원시 틱을 한 번만 훑어 전부 같은 bar 순서 위에 얹는다.

포함 프리미티브(8개, 전부 기존 파일에서 frozen 상수 그대로 import — 재최적화 없음):
footprint_imbalance, absorption(노이즈플로어 버전), cvd_divergence, large_trade(1m),
tape_vwap_fade(체결속도버스트x day-VWAP밴드), vwap_window(240봉 롤링 크로스),
trend_15m(market_structure), key_level_15m(스윙근접). + killzone(방향성 아닌 게이트).

제외: stop_run/large_trade_event/wall_proximity/iceberg_refill — 이벤트 레벨이거나
depth 필요라 60s bar 프리미티브 행렬에 안 맞음(스콥 밖, 별도 모듈에 이미 검증됨).

⚠️ DORMANT 확인용 스크립트. 조합 개수가 많아 다중검정 부담 큼 — 이 스윕 전용 BH-FDR
풀을 별도로 둔다(다른 배치와 안 섞음). 결과는 통계적 스크리닝일 뿐 실집행 근거 아님.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import deque
from itertools import combinations

from orderflow.aggregator import TAPE_WINDOW_SEC
from research.hypotheses.orderflow_context_gate import (
    VWAP_WINDOW_BUCKETS,
    _broadcast_15m_to_60s,
    build_key_level_filter,
    build_trend_filter,
    resample_bars,
)
from research.hypotheses.orderflow_futures import CVD_LOOKBACK_BUCKETS, FOOTPRINT_IMBALANCE_RATIO
from research.ict.primitives import killzone_indices
from research.strategies.orderflow_absorption import (
    ABSORPTION_DOMINANCE_RATIO,
    ABSORPTION_NOISE_FLOOR_MULTIPLIER,
    LARGE_TRADE_PERCENTILE,
    MIN_WARMUP_SAMPLES,
    ROLLING_WINDOW,
)
from research.strategies.orderflow_tape_vwap import (
    MIN_WARMUP_BARS as TAPE_MIN_WARMUP_BARS,
    TAPE_BURST_MULTIPLIER,
    TAPE_BURST_ROLLING_BARS,
    VWAP_BAND_SIGMA,
)
from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.cost_model import hl_effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics

BUCKET_SEC = 60
TARGET_NOTIONAL_USD = 1000.0  # absorption.py와 동일 원칙 — 심볼 가격스케일 무관 공정비교

PRIMITIVE_NAMES = (
    "footprint", "absorption", "cvd", "large_trade",
    "tape_vwap", "vwap_window", "trend_15m", "key_level_15m",
)


def load_ticks(paths: list[str]) -> list[dict]:
    ticks: list[dict] = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2.0 if n % 2 == 0 else s[mid]


def _percentile(sorted_asc: list[float], p: float) -> float:
    if not sorted_asc:
        return 0.0
    idx = min(len(sorted_asc) - 1, int(p * len(sorted_asc)))
    return sorted_asc[idx]


def _day_key(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y-%m-%d")


def build_feature_bars(ticks: list[dict], bucket_sec: int = BUCKET_SEC) -> dict:
    """원시 틱 단일 패스 → 60s bar 피처행렬(o/h/l/c/buy_vol/sell_vol/cvd/tape_speed/
    day-vwap+sd/버킷마감시점 median·p95 체결사이즈/대량체결 플래그). 전부 causal."""
    recent_trade_ts: deque[float] = deque()
    recent_trade_sizes: deque[float] = deque(maxlen=ROLLING_WINDOW)

    cum_v = cum_pv = cum_pv2 = 0.0
    cur_day: str | None = None
    cvd = 0.0

    bars: dict[int, dict] = {}
    order: list[int] = []
    cur_bar: int | None = None

    def _snapshot_close_stats(b: int) -> None:
        bars[b]["median_size_at_close"] = _median(list(recent_trade_sizes))
        bars[b]["p95_size_at_close"] = (
            _percentile(sorted(recent_trade_sizes), LARGE_TRADE_PERCENTILE)
            if len(recent_trade_sizes) >= MIN_WARMUP_SAMPLES else 0.0
        )

    for t in ticks:
        ts, price, size, side = t["ts"], t["price"], t["size"], t["side"]

        recent_trade_ts.append(ts)
        cutoff = ts - TAPE_WINDOW_SEC
        while recent_trade_ts and recent_trade_ts[0] < cutoff:
            recent_trade_ts.popleft()
        tape_speed = len(recent_trade_ts) / TAPE_WINDOW_SEC

        day = _day_key(ts)
        if day != cur_day:
            cur_day = day
            cum_v = cum_pv = cum_pv2 = 0.0
        cum_v += size
        cum_pv += price * size
        cum_pv2 += price * price * size

        b = int(ts // bucket_sec)
        if b != cur_bar:
            if cur_bar is not None:
                _snapshot_close_stats(cur_bar)
            cur_bar = b
            order.append(b)
            bars[b] = {
                "o": price, "h": price, "l": price, "c": price,
                "buy_vol": 0.0, "sell_vol": 0.0, "bucket_ts": float(b * bucket_sec),
                "has_large_buy": False, "has_large_sell": False,
            }

        bar = bars[b]
        bar["h"] = max(bar["h"], price)
        bar["l"] = min(bar["l"], price)
        bar["c"] = price
        if side == "buy":
            bar["buy_vol"] += size
        else:
            bar["sell_vol"] += size

        threshold = (
            _percentile(sorted(recent_trade_sizes), LARGE_TRADE_PERCENTILE)
            if len(recent_trade_sizes) >= MIN_WARMUP_SAMPLES else 0.0
        )
        if threshold > 0 and size > threshold:
            if side == "buy":
                bar["has_large_buy"] = True
            else:
                bar["has_large_sell"] = True
        recent_trade_sizes.append(size)

        cvd += size if side == "buy" else -size
        bar["cvd"] = cvd
        bar["tape_speed"] = tape_speed
        if cum_v > 0:
            vwap = cum_pv / cum_v
            variance = max(0.0, cum_pv2 / cum_v - vwap * vwap)
            bar["vwap"] = vwap
            bar["vwap_sd"] = variance ** 0.5

    if cur_bar is not None:
        _snapshot_close_stats(cur_bar)

    return {"order": order, "bars": bars}


def build_primitive_signals(order: list[int], bars: dict[int, dict]) -> dict:
    """8개 프리미티브 각각 (signals, eligible) — bar 인덱스(0..n-1) 공통 좌표."""
    n = len(order)
    closes = [bars[b]["c"] for b in order]

    # footprint_imbalance
    fp_sig: list[str] = []
    fp_elig: list[int] = []
    for i, b in enumerate(order):
        bv, sv = bars[b]["buy_vol"], bars[b]["sell_vol"]
        total = bv + sv
        sig = "HOLD"
        if total > 0:
            fp_elig.append(i)
            if bv / total >= FOOTPRINT_IMBALANCE_RATIO:
                sig = "BUY"
            elif sv / total >= FOOTPRINT_IMBALANCE_RATIO:
                sig = "SELL"
        fp_sig.append(sig)

    # absorption (노이즈플로어 버전, strategies/orderflow_absorption.py와 동일 판정식)
    ab_sig: list[str] = []
    ab_elig: list[int] = []
    for i, b in enumerate(order):
        bar = bars[b]
        bv, sv = bar["buy_vol"], bar["sell_vol"]
        total = bv + sv
        rm = bar.get("median_size_at_close", 0.0)
        sig = "HOLD"
        if rm > 0 and total >= rm * ABSORPTION_NOISE_FLOOR_MULTIPLIER:
            ab_elig.append(i)
            o, c = bar["o"], bar["c"]
            sell_ratio = sv / total if total else 0.0
            buy_ratio = bv / total if total else 0.0
            if sell_ratio >= ABSORPTION_DOMINANCE_RATIO and c >= o:
                sig = "BUY"
            elif buy_ratio >= ABSORPTION_DOMINANCE_RATIO and c <= o:
                sig = "SELL"
        ab_sig.append(sig)

    # cvd_divergence
    cvd_hist = [bars[b]["cvd"] for b in order]
    cvd_sig: list[str] = []
    cvd_elig: list[int] = []
    for i in range(n):
        sig = "HOLD"
        if i >= CVD_LOOKBACK_BUCKETS:
            cvd_elig.append(i)
            price_delta = closes[i] - closes[i - CVD_LOOKBACK_BUCKETS]
            cvd_delta = cvd_hist[i] - cvd_hist[i - CVD_LOOKBACK_BUCKETS]
            if price_delta < 0 and cvd_delta > 0:
                sig = "BUY"
            elif price_delta > 0 and cvd_delta < 0:
                sig = "SELL"
        cvd_sig.append(sig)

    # large_trade (1m 버킷, rolling p95)
    lt_sig: list[str] = []
    lt_elig: list[int] = []
    for i, b in enumerate(order):
        bar = bars[b]
        has_buy, has_sell = bar.get("has_large_buy", False), bar.get("has_large_sell", False)
        sig = "HOLD"
        if has_buy or has_sell:
            lt_elig.append(i)
            if has_buy and not has_sell:
                sig = "BUY"
            elif has_sell and not has_buy:
                sig = "SELL"
        lt_sig.append(sig)

    # tape_vwap_fade (체결속도버스트 x day-VWAP 밴드)
    tape_hist: deque[float] = deque(maxlen=TAPE_BURST_ROLLING_BARS)
    tv_sig: list[str] = []
    tv_elig: list[int] = []
    for i, b in enumerate(order):
        bar = bars[b]
        speed = bar.get("tape_speed", 0.0)
        sig = "HOLD"
        if len(tape_hist) >= TAPE_MIN_WARMUP_BARS and "vwap" in bar:
            median_speed = _median(list(tape_hist))
            if median_speed > 0 and speed >= TAPE_BURST_MULTIPLIER * median_speed:
                tv_elig.append(i)
                vwap, sd = bar["vwap"], bar["vwap_sd"]
                up1, dn1 = vwap + VWAP_BAND_SIGMA * sd, vwap - VWAP_BAND_SIGMA * sd
                if closes[i] > up1:
                    sig = "SELL"
                elif closes[i] < dn1:
                    sig = "BUY"
        tape_hist.append(speed)
        tv_sig.append(sig)

    # vwap_window (240봉 롤링 VWAP 크로스, context_gate.build_vwap_filter와 동일 공식)
    vw_sig: list[str] = []
    vw_elig: list[int] = []
    vols = [bars[b]["buy_vol"] + bars[b]["sell_vol"] for b in order]
    for i in range(n):
        start = max(0, i - VWAP_WINDOW_BUCKETS + 1)
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

    # trend_15m / key_level_15m (market_structure/swings, context_gate 그대로 재사용)
    bars_1m = [
        {"bucket_ts": bars[b]["bucket_ts"], "o": bars[b]["o"], "h": bars[b]["h"],
         "l": bars[b]["l"], "c": bars[b]["c"]}
        for b in order
    ]
    bars_15m = resample_bars(bars_1m, factor=15)
    bars_15m_ts = [x["bucket_ts"] for x in bars_15m]
    trend_15m = build_trend_filter(bars_15m)
    keylvl_15m = build_key_level_filter(bars_15m)
    order_ts = [bars[b]["bucket_ts"] for b in order]
    trend_60s = _broadcast_15m_to_60s(bars_15m_ts, trend_15m, order_ts)
    keylvl_60s = _broadcast_15m_to_60s(bars_15m_ts, keylvl_15m, order_ts)
    warmup_elig = [i for i in range(n) if bars_15m_ts and order_ts[i] >= bars_15m_ts[0]]

    kz = set(killzone_indices([int(ts) for ts in order_ts]))

    return {
        "closes": closes,
        "killzone": kz,
        "primitives": {
            "footprint": {"signals": fp_sig, "eligible": fp_elig},
            "absorption": {"signals": ab_sig, "eligible": ab_elig},
            "cvd": {"signals": cvd_sig, "eligible": cvd_elig},
            "large_trade": {"signals": lt_sig, "eligible": lt_elig},
            "tape_vwap": {"signals": tv_sig, "eligible": tv_elig},
            "vwap_window": {"signals": vw_sig, "eligible": vw_elig},
            "trend_15m": {"signals": trend_60s, "eligible": warmup_elig},
            "key_level_15m": {"signals": keylvl_60s, "eligible": warmup_elig},
        },
    }


def combine_and(sig_a: list[str], elig_a: list[int], sig_b: list[str], elig_b: list[int], n: int) -> dict:
    """페어와이즈 합의: 둘 다 판정가능하고 방향이 일치할 때만 그 방향, 아니면 HOLD.
    eligible = 둘 다 판정가능했던 인덱스(합의 여부 무관 — confluence.py와 동일 원칙)."""
    return combine_and_n([(sig_a, elig_a), (sig_b, elig_b)], n)


def combine_and_n(sig_elig_pairs: list[tuple[list[str], list[int]]], n: int) -> dict:
    """k개 프리미티브 전원 합의(AND): 전부 판정가능하고 방향이 전부 일치할 때만
    그 방향, 아니면 HOLD. eligible = 전원 판정가능했던 인덱스(합의 여부 무관)."""
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


def combine_majority_vote(prim: dict[str, dict], min_agree: int, n: int) -> dict:
    """전원합의(AND) 대신 다수결 — 8개 프리미티브 중 min_agree개 이상이 같은 방향으로
    투표하면(그 방향 표가 반대표보다 많을 때만) 신호. AND는 k가 커질수록 교집합이
    기하급수로 줄어 표본이 죽는 문제(3-way 스윕에서 확인)가 있어, 겹침 요구를 낮추면서도
    "여러 지표 동시 동의"를 보는 대안. eligible = 투표 가능한(그 시점 판정 가능한)
    프리미티브 수가 min_agree 이상이었던 인덱스(합의 여부 무관)."""
    elig_sets = {name: set(d["eligible"]) for name, d in prim.items()}
    signals: list[str] = []
    eligible: list[int] = []
    for i in range(n):
        buy_votes = sell_votes = total = 0
        for name, d in prim.items():
            if i in elig_sets[name]:
                total += 1
                if d["signals"][i] == "BUY":
                    buy_votes += 1
                elif d["signals"][i] == "SELL":
                    sell_votes += 1
        sig = "HOLD"
        if total >= min_agree:
            eligible.append(i)
            if buy_votes >= min_agree and buy_votes > sell_votes:
                sig = "BUY"
            elif sell_votes >= min_agree and sell_votes > buy_votes:
                sig = "SELL"
        signals.append(sig)
    return {"signals": signals, "eligible": eligible}


def combine_killzone_gate(sig: list[str], elig: list[int], kz: set[int], n: int) -> dict:
    """단일 프리미티브에 killzone 시간대 게이트만 추가 — 밖이면 신호 있어도 HOLD."""
    es = set(elig)
    signals: list[str] = []
    for i in range(n):
        sig_i = "HOLD"
        if i in es and i in kz:
            sig_i = sig[i]
        signals.append(sig_i)
    return {"signals": signals, "eligible": sorted(es)}


def _run_combo(symbol: str, combo_name: str, closes: list[float], data: dict,
               n_runs: int, seed: int, cost_bps: float) -> dict | None:
    signals, eligible = data["signals"], data["eligible"]
    if len(closes) < 10:
        return None
    trade_size = TARGET_NOTIONAL_USD / _median(closes)
    trades = simulate_long_short(closes, signals, trade_size, cost_bps)
    strat = trade_metrics(trades)
    if strat["num_trades"] == 0:
        return {"symbol": symbol, "combo": combo_name, "strategy": strat,
                "random": {"p_value": None, "percentile": None}, "eligible_count": len(eligible)}
    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=trade_size, cost_bps=cost_bps,
        eligible_indices=eligible, n_runs=n_runs, seed=seed,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)
    return {"symbol": symbol, "combo": combo_name, "strategy": strat,
            "random": pval, "eligible_count": len(eligible)}


def run_matrix(symbol: str, tick_paths: list[str], n_runs: int = 500, seed: int = 42) -> dict:
    """페어와이즈 AND(28) + killzone 게이트(8) = 36개 조합, 1개 심볼 기준."""
    ticks = load_ticks(tick_paths)
    if not ticks:
        return {"symbol": symbol, "blocked": True, "reason": "no tick data"}

    fb = build_feature_bars(ticks)
    order, bars = fb["order"], fb["bars"]
    if len(order) < 10:
        return {"symbol": symbol, "blocked": True, "reason": f"{len(order)}봉뿐 — 최소 표본 미달"}

    data = build_primitive_signals(order, bars)
    closes, kz, prim = data["closes"], data["killzone"], data["primitives"]
    n = len(closes)
    cost_bps = hl_effective_cost_bps("major", taker=True)

    results: list[dict] = []

    for name_a, name_b in combinations(PRIMITIVE_NAMES, 2):
        a, b = prim[name_a], prim[name_b]
        combo = combine_and(a["signals"], a["eligible"], b["signals"], b["eligible"], n)
        r = _run_combo(symbol, f"{name_a}+{name_b}", closes, combo, n_runs, seed, cost_bps)
        if r:
            results.append(r)

    for name in PRIMITIVE_NAMES:
        p = prim[name]
        combo = combine_killzone_gate(p["signals"], p["eligible"], kz, n)
        r = _run_combo(symbol, f"{name}+killzone", closes, combo, n_runs, seed, cost_bps)
        if r:
            results.append(r)

    return {"symbol": symbol, "blocked": False, "n_bars": n, "n_ticks": len(ticks), "results": results}


def run_majority_matrix(symbol: str, tick_paths: list[str], thresholds: tuple[int, ...] = (3, 4, 5, 6),
                         n_runs: int = 500, seed: int = 42) -> dict:
    """8개 프리미티브 다수결 스윕(min_agree in thresholds). AND처럼 표본이 죽지 않게
    설계 — 겹침 요구를 낮춰 "여러 지표 동시 동의" 신호가 실제로 존재하는지 확인."""
    ticks = load_ticks(tick_paths)
    if not ticks:
        return {"symbol": symbol, "blocked": True, "reason": "no tick data"}

    fb = build_feature_bars(ticks)
    order, bars = fb["order"], fb["bars"]
    if len(order) < 10:
        return {"symbol": symbol, "blocked": True, "reason": f"{len(order)}봉뿐 — 최소 표본 미달"}

    data = build_primitive_signals(order, bars)
    closes, prim = data["closes"], data["primitives"]
    n = len(closes)
    cost_bps = hl_effective_cost_bps("major", taker=True)

    results: list[dict] = []
    for min_agree in thresholds:
        combo = combine_majority_vote(prim, min_agree, n)
        r = _run_combo(symbol, f"majority>={min_agree}of8", closes, combo, n_runs, seed, cost_bps)
        if r:
            results.append(r)

    return {"symbol": symbol, "blocked": False, "n_bars": n, "n_ticks": len(ticks), "results": results}


def run_matrix_k(symbol: str, tick_paths: list[str], k: int, n_runs: int = 500, seed: int = 42) -> dict:
    """프리미티브 k개 전원합의 AND 조합 스윕. C(8,k)개, 1개 심볼 기준."""
    ticks = load_ticks(tick_paths)
    if not ticks:
        return {"symbol": symbol, "blocked": True, "reason": "no tick data"}

    fb = build_feature_bars(ticks)
    order, bars = fb["order"], fb["bars"]
    if len(order) < 10:
        return {"symbol": symbol, "blocked": True, "reason": f"{len(order)}봉뿐 — 최소 표본 미달"}

    data = build_primitive_signals(order, bars)
    closes, prim = data["closes"], data["primitives"]
    n = len(closes)
    cost_bps = hl_effective_cost_bps("major", taker=True)

    results: list[dict] = []
    for names in combinations(PRIMITIVE_NAMES, k):
        pairs = [(prim[name]["signals"], prim[name]["eligible"]) for name in names]
        combo = combine_and_n(pairs, n)
        r = _run_combo(symbol, "+".join(names), closes, combo, n_runs, seed, cost_bps)
        if r:
            results.append(r)

    return {"symbol": symbol, "blocked": False, "n_bars": n, "n_ticks": len(ticks), "results": results}
