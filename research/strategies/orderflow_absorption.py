"""가설: 오더플로우 흡수(Absorption) 신호 — 매도 우세인데 가격 안 밀리면 롱, 매수
우세인데 가격 안 오르면 숏 (`/orderflow` 대시보드의 흡수 마커와 동일 판정 로직).

⚠️ DORMANT 모듈 — 검증된 알파 아님. 임계값은 프론트(`lib/orderflow-data.ts`)와 동일
고정값 — 이 백테스트용으로 최적화하지 않음(사전에 시각화 목적으로 정해진 값을 그대로
검정). 데이터는 `research/data/hl_orderflow_tick/{SYMBOL}_*.jsonl` 틱 — 2026-07-10~11
2일치뿐이라 표본 협소, 1차 생존 판정용이며 최종 검증 아님.

프론트와의 유일한 의도적 차이: 프론트는 라이브 렌더용으로 rolling median 스냅샷 1개를
전체 화면에 재사용(순수 시각화라 문제 없음). 여기선 lookahead 방지 위해 각 버킷 종료
시점까지의 causal median을 그때그때 재계산한다.
"""
from __future__ import annotations

import bisect
import json
import random as _random
from collections import deque

from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.cost_model import hl_effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics
from research.reports.alpha_report import build_report

# 고정 파라미터 — 프론트와 동일값, 최적화 금지
ROLLING_WINDOW = 200
MIN_WARMUP_SAMPLES = 20
LARGE_TRADE_PERCENTILE = 0.95
ABSORPTION_DOMINANCE_RATIO = 0.7
ABSORPTION_NOISE_FLOOR_MULTIPLIER = 10.0
BUCKET_SEC = 60

DEFAULTS = {"trade_size": 10.0}


def load_ticks(paths: list[str]) -> list[dict]:
    """여러 일자 jsonl 파일 → 시간순 정렬된 틱 리스트."""
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
    """대량체결 판정용 p95. `lib/orderflow-data.ts`의 percentile()과 동일 규칙."""
    idx = min(len(sorted_asc) - 1, int(p * len(sorted_asc)))
    return sorted_asc[idx]


def build_bars_and_signals(ticks: list[dict], bucket_sec: int = BUCKET_SEC) -> dict:
    """틱 → 1분봉(open/close) + causal 흡수 신호(BUY/SELL/HOLD) + eligible(판정 가능 버킷).

    대량체결 트래커(median 롤링윈도우)를 틱 순서대로 굴려 lookahead 없이 각 버킷 종료
    시점의 median으로 그 버킷의 흡수 판정을 한다 — `lib/orderflow-data.ts`의
    `applyLargeTradeTracking`/`detectAbsorption`과 동일 규칙, 동일 임계값."""
    recent_sizes: deque[float] = deque(maxlen=ROLLING_WINDOW)

    bucket_open: dict[int, float] = {}
    bucket_close: dict[int, float] = {}
    bucket_buy: dict[int, float] = {}
    bucket_sell: dict[int, float] = {}
    bucket_order: list[int] = []
    median_at_close: dict[int, float] = {}

    cur_bucket: int | None = None
    for t in ticks:
        b = int(t["ts"] // bucket_sec)
        if b != cur_bucket:
            if cur_bucket is not None:
                median_at_close[cur_bucket] = _median(list(recent_sizes))
            cur_bucket = b
            bucket_order.append(b)
            bucket_open[b] = t["price"]
        bucket_close[b] = t["price"]

        size = t["size"]
        # 대량체결도 표본에서 제외하지 않는다 — 제외 시 median이 최솟값 근처로
        # 폭주 붕괴하는 버그(2026-07-11 확인, 대량체결 트래커와 동일 원인).
        recent_sizes.append(size)

        if t["side"] == "buy":
            bucket_buy[b] = bucket_buy.get(b, 0.0) + size
        else:
            bucket_sell[b] = bucket_sell.get(b, 0.0) + size

    if cur_bucket is not None:
        median_at_close[cur_bucket] = _median(list(recent_sizes))

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []

    for i, b in enumerate(bucket_order):
        closes.append(bucket_close[b])
        rm = median_at_close.get(b, 0.0)
        buy = bucket_buy.get(b, 0.0)
        sell = bucket_sell.get(b, 0.0)
        total = buy + sell
        sig = "HOLD"
        if rm > 0:
            noise_floor = rm * ABSORPTION_NOISE_FLOOR_MULTIPLIER
            if total >= noise_floor:
                eligible.append(i)
                sell_ratio = sell / total
                buy_ratio = buy / total
                o, c = bucket_open[b], bucket_close[b]
                if sell_ratio >= ABSORPTION_DOMINANCE_RATIO and c >= o:
                    sig = "BUY"   # 매도 우세인데 안 밀림 = 매도 흡수 = 강세
                elif buy_ratio >= ABSORPTION_DOMINANCE_RATIO and c <= o:
                    sig = "SELL"  # 매수 우세인데 안 오름 = 매수 흡수 = 약세
        signals.append(sig)

    return {"closes": closes, "signals": signals, "eligible": eligible}


def build_bars_and_large_trade_signals(ticks: list[dict], bucket_sec: int = BUCKET_SEC) -> dict:
    """틱 → 1분봉(close) + 대량체결(rolling p95) 방향 신호(BUY/SELL/HOLD).

    한 버킷에 대량 매수만 있으면 BUY, 대량 매도만 있으면 SELL, 둘 다/없음이면 HOLD.
    포지션 청산은 반대 신호가 다시 뜰 때(`simulate_long_short` flip 규약)."""
    recent_sizes: deque[float] = deque(maxlen=ROLLING_WINDOW)

    bucket_close: dict[int, float] = {}
    bucket_order: list[int] = []
    bucket_large_buy: dict[int, bool] = {}
    bucket_large_sell: dict[int, bool] = {}

    cur_bucket: int | None = None
    for t in ticks:
        b = int(t["ts"] // bucket_sec)
        if b != cur_bucket:
            cur_bucket = b
            bucket_order.append(b)
        bucket_close[b] = t["price"]

        size = t["size"]
        threshold = _percentile(sorted(recent_sizes), LARGE_TRADE_PERCENTILE) if len(recent_sizes) >= MIN_WARMUP_SAMPLES else 0.0
        is_large = threshold > 0 and size > threshold
        if is_large:
            if t["side"] == "buy":
                bucket_large_buy[b] = True
            else:
                bucket_large_sell[b] = True
        recent_sizes.append(size)

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, b in enumerate(bucket_order):
        closes.append(bucket_close[b])
        has_buy = bucket_large_buy.get(b, False)
        has_sell = bucket_large_sell.get(b, False)
        if has_buy or has_sell:
            eligible.append(i)
        if has_buy and not has_sell:
            signals.append("BUY")
        elif has_sell and not has_buy:
            signals.append("SELL")
        else:
            signals.append("HOLD")

    return {"closes": closes, "signals": signals, "eligible": eligible}


def run_large_trade_hypothesis(
    symbol: str,
    tick_paths: list[str],
    params: dict | None = None,
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
    keep_random: bool = False,
) -> dict:
    """대량체결(rolling p95) 방향 추종 신호 검증. 틱 데이터 없음 → BLOCKED 리포트."""
    p = {**DEFAULTS, **(params or {})}
    ticks = load_ticks(tick_paths)
    if not ticks:
        return _blocked(symbol, "no tick data — collector 확인 필요", write_report)

    data = build_bars_and_large_trade_signals(ticks)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < 10:
        return _blocked(symbol, f"틱→버킷 변환 후 {len(closes)}봉뿐 — 최소 표본 미달", write_report)

    cost_bps = hl_effective_cost_bps("major", taker=True)
    trades = simulate_long_short(closes, signals, p["trade_size"], cost_bps)
    strat = trade_metrics(trades)

    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=p["trade_size"], cost_bps=cost_bps,
        eligible_indices=eligible, n_runs=n_runs, seed=seed,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)

    result = {
        "symbol": symbol, "blocked": False,
        "strategy": strat, "random": pval,
        "n_bars": len(closes), "eligible_count": len(eligible),
        "n_ticks": len(ticks),
    }
    if keep_random:
        result["random_stats"] = rnd
    if write_report:
        rep = build_report(
            name=f"orderflow_large_trade_{symbol}",
            hypothesis=(
                "대량체결(rolling p95) 방향 추종: 대량매수 뜨면 롱, 대량매도 뜨면 숏 "
                "(고정임계·미최적화, 대시보드 버블 마커와 동일 로직)"
            ),
            universe=[symbol], timeframe="1m",
            cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
            strategy=strat, random_pval=pval,
            naive={"total_pnl": None, "note": "대량체결 추종은 buy&hold 비교 부적합 → random 분포가 주판정"},
            walk_forward_result={"summary": {}},
            is_harness_dryrun=False,
            extra={
                "n_bars": len(closes), "eligible_count": len(eligible), "n_ticks": len(ticks),
                "note": (
                    "DORMANT hypothesis. NOT validated alpha. 2일치 틱 데이터뿐 — "
                    "1차 생존 판정용, 최종 검증 아님. 워크포워드 불가(표본 부족)."
                ),
            },
        )
        result["report"] = rep
    return result


def _large_trade_events(ticks: list[dict]) -> list[dict]:
    """대량체결(rolling p95) 이벤트만 추출: {idx, ts, side, price}. idx=ticks 내 인덱스.

    `lib/orderflow-data.ts`의 `applyLargeTradeTracking`과 동일 규칙(2026-07-11 수정판):
    표본 제외 없음(제외 시 median/percentile이 최솟값 근처로 폭주 붕괴하는 버그가 있었음),
    고정배수(median*3) 대신 rolling window 자체의 p95를 문턱으로 사용."""
    recent_sizes: deque[float] = deque(maxlen=ROLLING_WINDOW)
    events: list[dict] = []
    for i, t in enumerate(ticks):
        size = t["size"]
        threshold = _percentile(sorted(recent_sizes), LARGE_TRADE_PERCENTILE) if len(recent_sizes) >= MIN_WARMUP_SAMPLES else 0.0
        is_large = threshold > 0 and size > threshold
        if is_large:
            events.append({"idx": i, "ts": t["ts"], "side": t["side"], "price": t["price"]})
        recent_sizes.append(size)
    return events


def run_large_trade_event_hypothesis(
    symbol: str,
    tick_paths: list[str],
    hold_seconds_list: tuple[float, ...] = (10.0, 30.0, 60.0),
    trade_size: float = 10.0,
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
) -> dict:
    """대량체결 방향 → 즉시 진입, N초 뒤 고정청산. 1분봉 집계판(run_large_trade_hypothesis)의
    후속 재설계 — 1분에 틱 100개+ 몰리는 BTC/ETH에서 매수/매도 대량체결이 같은 분봉에
    동시발생해 방향이 상쇄되며 신호가 0~1건만 남던 결함을 개별 이벤트 단위로 해소.

    랜덤 베이스라인은 진입 '시점'을 실제 대량체결 발생 시점 그대로 고정하고 '방향'만
    run마다 동전던지기로 재배정 — '이 순간에 진입하는 것 자체가 유리한가'가 아니라
    '체결 side(매수/매도 우세)가 이후 가격방향을 예측하는가'만 순수 분리해서 검정."""
    ticks = load_ticks(tick_paths)
    if not ticks:
        return _blocked(symbol, "no tick data — collector 확인 필요", write_report)

    events = _large_trade_events(ticks)
    if len(events) < 10:
        return _blocked(symbol, f"대량체결 이벤트 {len(events)}건뿐 — 최소 표본 미달", write_report)

    ts_arr = [t["ts"] for t in ticks]
    px_arr = [t["price"] for t in ticks]
    cost_bps = hl_effective_cost_bps("major", taker=True)
    rng = _random.Random(seed)

    horizons: dict[str, dict] = {}
    for hold_sec in hold_seconds_list:
        precomputed = []  # (side_sign, entry_px, exit_px, cost)
        for ev in events:
            entry_idx, entry_px = ev["idx"], ev["price"]
            exit_ts = ev["ts"] + hold_sec
            exit_idx = min(bisect.bisect_left(ts_arr, exit_ts, entry_idx), len(ts_arr) - 1)
            exit_px = px_arr[exit_idx]
            cost = (abs(entry_px) + abs(exit_px)) * trade_size * cost_bps / 10_000.0
            side_sign = 1.0 if ev["side"] == "buy" else -1.0
            precomputed.append((side_sign, entry_px, exit_px, cost))

        actual_pnls = [sign * (ex - en) * trade_size - c for sign, en, ex, c in precomputed]
        strat = trade_metrics([{"pnl": p} for p in actual_pnls])

        random_totals = []
        for _ in range(n_runs):
            total = 0.0
            for _sign, en, ex, c in precomputed:
                rsign = rng.choice((1.0, -1.0))
                total += rsign * (ex - en) * trade_size - c
            random_totals.append(round(total, 6))
        pval = empirical_p_value(strat["total_pnl"], random_totals)

        horizons[f"{int(hold_sec)}s"] = {"strategy": strat, "random": pval}

    result = {"symbol": symbol, "blocked": False, "n_events": len(events),
              "n_ticks": len(ticks), "horizons": horizons}

    if write_report:
        for h_key, h_res in horizons.items():
            rep = build_report(
                name=f"orderflow_large_trade_event_{symbol}_{h_key}",
                hypothesis=(
                    f"대량체결(rolling p95) 방향 즉시추종, {h_key} 고정청산 — "
                    "진입시점 실제 대량체결 시점 고정, random은 방향만 재배정(방향 예측력 순수검정)"
                ),
                universe=[symbol], timeframe="tick",
                cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
                strategy=h_res["strategy"], random_pval=h_res["random"],
                naive={"total_pnl": None, "note": "이벤트기반 방향추종 buy&hold 비교 부적합 → random 분포가 주판정"},
                walk_forward_result={"summary": {}},
                is_harness_dryrun=False,
                extra={
                    "n_events": len(events), "n_ticks": len(ticks), "hold_seconds": h_key,
                    "note": (
                        "DORMANT hypothesis. NOT validated alpha. 2일치 틱 데이터뿐 — "
                        "1차 생존 판정용, 최종 검증 아님. random은 시점 고정+방향만 셔플."
                    ),
                },
            )
            h_res["report"] = rep
    return result


def run_hypothesis(
    symbol: str,
    tick_paths: list[str],
    params: dict | None = None,
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
    keep_random: bool = False,
) -> dict:
    """흡수 신호 검증 실행. 틱 데이터 없음 → BLOCKED 리포트."""
    p = {**DEFAULTS, **(params or {})}
    ticks = load_ticks(tick_paths)
    if not ticks:
        return _blocked(symbol, "no tick data — collector 확인 필요", write_report)

    data = build_bars_and_signals(ticks)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < 10:
        return _blocked(symbol, f"틱→버킷 변환 후 {len(closes)}봉뿐 — 최소 표본 미달", write_report)

    cost_bps = hl_effective_cost_bps("major", taker=True)
    trades = simulate_long_short(closes, signals, p["trade_size"], cost_bps)
    strat = trade_metrics(trades)

    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=p["trade_size"], cost_bps=cost_bps,
        eligible_indices=eligible, n_runs=n_runs, seed=seed,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)

    result = {
        "symbol": symbol, "blocked": False,
        "strategy": strat, "random": pval,
        "n_bars": len(closes), "eligible_count": len(eligible),
        "n_ticks": len(ticks),
    }
    if keep_random:
        result["random_stats"] = rnd
    if write_report:
        rep = build_report(
            name=f"orderflow_absorption_{symbol}",
            hypothesis=(
                "1분봉 오더플로우 흡수: 매도우세(>=70%)+가격안밀림=롱, "
                "매수우세(>=70%)+가격안오름=숏 (고정임계·미최적화, 대시보드 흡수마커와 동일 로직)"
            ),
            universe=[symbol], timeframe="1m",
            cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
            strategy=strat, random_pval=pval,
            naive={"total_pnl": None, "note": "흡수 신호는 buy&hold 비교 부적합 → random 분포가 주판정"},
            walk_forward_result={"summary": {}},
            is_harness_dryrun=False,
            extra={
                "n_bars": len(closes), "eligible_count": len(eligible), "n_ticks": len(ticks),
                "note": (
                    "DORMANT hypothesis. NOT validated alpha. 2일치 틱 데이터뿐 — "
                    "1차 생존 판정용, 최종 검증 아님. 워크포워드 불가(표본 부족)."
                ),
            },
        )
        result["report"] = rep
    return result


def _blocked(symbol: str, msg: str, write_report: bool) -> dict:
    res = {"symbol": symbol, "blocked": True, "reason": msg,
           "verdict": "BLOCKED: " + msg}
    if write_report:
        import os
        from research.reports.alpha_report import REPORT_DIR
        os.makedirs(REPORT_DIR, exist_ok=True)
        base = os.path.join(REPORT_DIR, f"orderflow_absorption_{symbol}")
        with open(base + ".json", "w") as f:
            json.dump(res, f, indent=2)
        with open(base + ".md", "w") as f:
            f.write(f"# Orderflow Absorption — {symbol}\n\n**BLOCKED.** {msg}\n")
    return res
