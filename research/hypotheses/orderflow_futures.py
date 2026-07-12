"""가설: NQ/MNQ 오더플로우 시그널 5종 — footprint 불균형, CVD 다이버전스,
stop-run 패턴, heatmap 유동성벽 근접, iceberg refill.

⚠️ DORMANT 모듈 — 검증된 알파 아님. 임계값은 프론트(`lib/orderflow-data.ts`)와
동일 고정값 원칙(백테스트용으로 재최적화하지 않음). 입력은
`research/run_ib_orderflow_tick_collect.py`가 저장하는 footprint_delta/
heatmap_delta jsonl — 라이브 대시보드와 동일한 OrderflowAggregator 버킷팅을
거친 값이므로 원시 틱과 1:1은 아니다(footprint 60s 버킷, heatmap 2s 버킷).

footprint 불균형 + CVD 다이버전스 + heatmap 유동성벽 근접 + iceberg refill +
stop-run(이벤트 레벨) 까지 구현하고, 5신호 x 심볼 전체를 BH-FDR로 종합 판정하는
검증 오케스트레이션(run_signal_hypothesis/run_stop_run_hypothesis/run_all_hypotheses)까지 포함한다.
"""
from __future__ import annotations

import json

from research.reports.alpha_report import build_report
from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.cost_model import ib_futures_effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics

FOOTPRINT_IMBALANCE_RATIO = 0.7  # lib/orderflow-data.ts 흡수 판정 임계값과 동일 — 고정 파라미터, 최적화 금지
CVD_LOOKBACK_BUCKETS = 5  # 고정 파라미터, 최적화 금지

DEFAULTS = {"trade_size": 1.0}  # 계약수(contracts) — futures는 notional이 multiplier로 이미 반영됨
NOTIONAL_MULTIPLIER = {"NQ": 20.0, "MNQ": 2.0}  # IB_FUTURES_TICK_VALUE_USD / tick_size(0.25)


def load_deltas(paths: list[str]) -> list[dict]:
    """여러 일자 jsonl 파일 -> bucket_ts 기준 정렬된 delta 리스트."""
    deltas: list[dict] = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    deltas.append(json.loads(line))
    deltas.sort(key=lambda d: d.get("bucket_ts", d.get("ts", 0.0)))
    return deltas


def _footprint_buckets(deltas: list[dict]) -> tuple[list[float], dict[float, float], dict[float, float], dict[float, float]]:
    """footprint_delta만 골라 버킷 순서 + 버킷별 buy_vol/sell_vol 누적."""
    order: list[float] = []
    seen: set[float] = set()
    buy: dict[float, float] = {}
    sell: dict[float, float] = {}
    last_price: dict[float, float] = {}
    for d in deltas:
        if d.get("type") != "footprint_delta":
            continue
        b = d["bucket_ts"]
        if b not in seen:
            seen.add(b)
            order.append(b)
        if d["side"] == "buy":
            buy[b] = buy.get(b, 0.0) + d["delta_vol"]
        else:
            sell[b] = sell.get(b, 0.0) + d["delta_vol"]
        last_price[b] = d["price"]
    return order, buy, sell, last_price


def build_footprint_imbalance_signals(deltas: list[dict], imbalance_ratio: float = FOOTPRINT_IMBALANCE_RATIO) -> dict:
    """버킷별 buy/sell 볼륨 비율이 imbalance_ratio 넘으면 그 방향으로 BUY/SELL."""
    order, buy, sell, last_price = _footprint_buckets(deltas)

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, b in enumerate(order):
        bv, sv = buy.get(b, 0.0), sell.get(b, 0.0)
        total = bv + sv
        closes.append(last_price[b])
        sig = "HOLD"
        if total > 0:
            eligible.append(i)
            if bv / total >= imbalance_ratio:
                sig = "BUY"
            elif sv / total >= imbalance_ratio:
                sig = "SELL"
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}


def build_cvd_divergence_signals(deltas: list[dict], lookback_buckets: int = CVD_LOOKBACK_BUCKETS) -> dict:
    """누적 delta(CVD)가 lookback 구간 동안 가격과 반대 방향이면 다이버전스 신호.

    가격 하락+CVD 상승 -> BUY(매도세인 척하지만 실제 매수 우위 -> 반등 기대).
    가격 상승+CVD 하락 -> SELL. lookback 미달 버킷은 HOLD/not eligible.
    eligible은 "다이버전스가 실제로 뜬 인덱스"가 아니라 build_footprint_imbalance_signals와
    동일하게 "판정 가능했던 버킷"(i >= lookback_buckets) 전체 — HOLD로 끝난 버킷도 포함."""
    order, buy, sell, last_price = _footprint_buckets(deltas)

    cvd = 0.0
    cvd_history: list[float] = []
    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, b in enumerate(order):
        cvd += buy.get(b, 0.0) - sell.get(b, 0.0)
        cvd_history.append(cvd)
        closes.append(last_price[b])

        sig = "HOLD"
        if i >= lookback_buckets:
            eligible.append(i)
            price_delta = closes[i] - closes[i - lookback_buckets]
            cvd_delta = cvd_history[i] - cvd_history[i - lookback_buckets]
            if price_delta < 0 and cvd_delta > 0:
                sig = "BUY"
            elif price_delta > 0 and cvd_delta < 0:
                sig = "SELL"
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}


WALL_SIZE_THRESHOLD = 15.0  # lib/orderflow-data.ts 히트맵 하이라이트 임계값과 동일 — 고정 파라미터, 최적화 금지
WALL_PROXIMITY_TICKS = 4  # 고정 파라미터, 최적화 금지
ICEBERG_REFILL_RATIO = 0.8  # 고정 파라미터, 최적화 금지
ICEBERG_MIN_DEPLETION = 3.0  # 고정 파라미터, 최적화 금지


def _heatmap_buckets(deltas: list[dict]) -> list[dict]:
    """heatmap_delta만 골라 ts 오름차순 그대로(이미 load_deltas가 정렬함)."""
    return [d for d in deltas if d.get("type") == "heatmap_delta"]


def build_wall_proximity_signals(
    deltas: list[dict],
    wall_size_threshold: float = WALL_SIZE_THRESHOLD,
    proximity_ticks: int = WALL_PROXIMITY_TICKS,
    tick_size: float = 0.25,
) -> dict:
    """대형 잔량 벽 근처로 가격 접근 시 벽 방향으로 신호.
    가격이 벽보다 낮고 근접하면(벽=매수벽, 지지) BUY. 벽보다 높고 근접하면(매도벽, 저항) SELL.

    '현재가'는 각 heatmap 스냅샷 시각의 최소/최대 관측 price 중간값으로 근사한다
    (진짜 체결가는 footprint_delta 쪽에 있으나, 이 신호는 heatmap만으로 독립 검증하기
    위해 heatmap 관측 price 레인지의 중앙을 현재가 프록시로 쓴다).

    eligible은 build_footprint_imbalance_signals/build_cvd_divergence_signals와 동일하게
    "판정 가능했던 버킷"(threshold 이상 벽이 스냅샷에 하나라도 있는 버킷) 전체 —
    벽이 있었지만 근접 범위 밖이라 HOLD로 끝난 버킷도 포함한다. "신호가 뜬 버킷"만
    담으면 안 된다."""
    rows = _heatmap_buckets(deltas)
    by_ts: dict[float, list[dict]] = {}
    order: list[float] = []
    for r in rows:
        if r["ts"] not in by_ts:
            by_ts[r["ts"]] = []
            order.append(r["ts"])
        by_ts[r["ts"]].append(r)

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, ts in enumerate(order):
        levels = by_ts[ts]
        prices = [lv["price"] for lv in levels]
        mid = (min(prices) + max(prices)) / 2.0
        closes.append(mid)

        walls = [lv for lv in levels if lv["size"] >= wall_size_threshold]
        sig = "HOLD"
        if walls:
            eligible.append(i)
            for w in walls:
                dist_ticks = abs(w["price"] - mid) / tick_size
                if dist_ticks <= proximity_ticks:
                    sig = "BUY" if w["price"] < mid else "SELL"
                    break
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}


def build_iceberg_refill_signals(
    deltas: list[dict],
    refill_ratio: float = ICEBERG_REFILL_RATIO,
    min_depletion: float = ICEBERG_MIN_DEPLETION,
) -> dict:
    """같은 가격 레벨에서 잔량이 급감했다가 즉시 재충전되면 iceberg 주문으로 간주.
    재충전 방향(그 가격이 현재가보다 낮으면 매수벽 iceberg=BUY, 높으면 SELL)으로 신호.

    eligible은 "소진->재충전 패턴이 실제로 뜬 버킷"이 아니라 "판정에 필요한 이력
    (같은 가격에서 최소 3개 관측: base/depleted/refilled)이 갖춰져 판정 가능했던
    버킷" 전체 — footprint_imbalance/cvd_divergence/wall_proximity와 동일 규칙."""
    rows = _heatmap_buckets(deltas)
    by_ts: dict[float, list[dict]] = {}
    order: list[float] = []
    for r in rows:
        if r["ts"] not in by_ts:
            by_ts[r["ts"]] = []
            order.append(r["ts"])
        by_ts[r["ts"]].append(r)

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, ts in enumerate(order):
        levels = by_ts[ts]
        prices = [lv["price"] for lv in levels]
        mid = (min(prices) + max(prices)) / 2.0
        closes.append(mid)

        sig = "HOLD"
        judged = False
        # 소진->재충전은 같은 가격에서 최소 3개 관측(base, depleted, refilled)이 필요.
        if i >= 2:
            for lv in levels:
                price = lv["price"]
                hist = [d["size"] for d in rows if d["price"] == price and d["ts"] <= ts]
                if len(hist) < 3:
                    continue
                judged = True
                base, depleted_size, refilled_size = hist[-3], hist[-2], hist[-1]
                if base - depleted_size >= min_depletion and refilled_size >= base * refill_ratio:
                    sig = "BUY" if price < mid else "SELL"
                    break
        if judged:
            eligible.append(i)
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}


STOP_RUN_SPIKE_RATIO = 3.0  # 고정 파라미터, 최적화 금지
STOP_RUN_LOOKBACK_BUCKETS = 10  # 고정 파라미터, 최적화 금지


def stop_run_events(
    deltas: list[dict],
    spike_ratio: float = STOP_RUN_SPIKE_RATIO,
    lookback_buckets: int = STOP_RUN_LOOKBACK_BUCKETS,
) -> list[dict]:
    """직전 lookback_buckets 평균 대비 총 거래량이 spike_ratio배 이상 튄 버킷을
    스탑런(청산 유발성 급변동) 이벤트로 간주. side는 그 버킷의 우세 방향.

    다른 build_*_signals류(bar-index 방식, HOLD 포함 전체 길이 반환)와 다르게
    이벤트가 발생한 버킷만 담은 이벤트 리스트를 반환한다 —
    research/strategies/orderflow_absorption.py의 _large_trade_events와 동일 패턴."""
    order, buy, sell, last_price = _footprint_buckets(deltas)
    totals = [buy.get(b, 0.0) + sell.get(b, 0.0) for b in order]

    events: list[dict] = []
    for i, b in enumerate(order):
        if i < lookback_buckets:
            continue
        window = totals[i - lookback_buckets:i]
        avg = sum(window) / len(window) if window else 0.0
        if avg > 0 and totals[i] >= avg * spike_ratio:
            bv, sv = buy.get(b, 0.0), sell.get(b, 0.0)
            side = "buy" if bv >= sv else "sell"
            events.append({"idx": i, "bucket_ts": b, "side": side, "price": last_price[b]})
    return events


SIGNAL_BUILDERS = {
    "footprint_imbalance": build_footprint_imbalance_signals,
    "cvd_divergence": build_cvd_divergence_signals,
    "wall_proximity": build_wall_proximity_signals,
    "iceberg_refill": build_iceberg_refill_signals,
}

HYPOTHESIS_TEXT = {
    "footprint_imbalance": f"1분봉 footprint 매수/매도 비율 {FOOTPRINT_IMBALANCE_RATIO} 이상 우세 방향 추종",
    "cvd_divergence": f"누적델타(CVD) {CVD_LOOKBACK_BUCKETS}버킷 다이버전스 역추세 진입",
    "wall_proximity": f"heatmap 대형벽({WALL_SIZE_THRESHOLD} 이상) {WALL_PROXIMITY_TICKS}틱 근접 시 벽 방향 진입",
    "iceberg_refill": f"동일가 잔량 급감후 재충전({int(ICEBERG_REFILL_RATIO*100)}% 이상) 패턴 추종",
}


def run_signal_hypothesis(
    symbol: str,
    signal_name: str,
    delta_paths: list[str],
    params: dict | None = None,
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
) -> dict:
    """bar 기반 4개 시그널(footprint_imbalance/cvd_divergence/wall_proximity/iceberg_refill)
    공통 실행 경로. 데이터 없음/표본 부족 -> BLOCKED 리포트."""
    if signal_name not in SIGNAL_BUILDERS:
        raise ValueError(f"unknown signal_name: {signal_name}")

    p = {**DEFAULTS, **(params or {})}
    deltas = load_deltas(delta_paths)
    if not deltas:
        return _blocked(symbol, signal_name, "no delta data — collector 확인 필요", write_report)

    data = SIGNAL_BUILDERS[signal_name](deltas)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < 10:
        return _blocked(symbol, signal_name, f"델타→버킷 변환 후 {len(closes)}봉뿐 — 최소 표본 미달", write_report)

    notional = closes[-1] * NOTIONAL_MULTIPLIER.get(symbol, 20.0)
    cost_bps = ib_futures_effective_cost_bps(symbol, notional)
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
        "symbol": symbol, "signal": signal_name, "blocked": False,
        "strategy": strat, "random": pval,
        "n_bars": len(closes), "eligible_count": len(eligible),
    }
    if write_report:
        rep = build_report(
            name=f"orderflow_futures_{signal_name}_{symbol}",
            hypothesis=HYPOTHESIS_TEXT[signal_name],
            universe=[symbol], timeframe="1m/2s(신호별 상이)",
            cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
            strategy=strat, random_pval=pval,
            naive={"total_pnl": None, "note": "오더플로우 신호는 buy&hold 비교 부적합 -> random 분포가 주판정"},
            walk_forward_result={"summary": {}},
            is_harness_dryrun=False,
            extra={
                "n_bars": len(closes), "eligible_count": len(eligible),
                "note": "DORMANT hypothesis. NOT validated alpha. 1차 생존 판정용.",
            },
        )
        result["report"] = rep
    return result


def run_stop_run_hypothesis(
    symbol: str,
    delta_paths: list[str],
    hold_buckets_list: tuple[int, ...] = (1, 3, 5),
    trade_size: float = 1.0,
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
) -> dict:
    """스탑런 이벤트 방향 즉시추종, N버킷 뒤 고정청산. random은 방향만 셔플
    (orderflow_absorption.run_large_trade_event_hypothesis와 동일 검정 설계)."""
    deltas = load_deltas(delta_paths)
    if not deltas:
        return _blocked(symbol, "stop_run", "no delta data — collector 확인 필요", write_report)

    events = stop_run_events(deltas)
    if len(events) < 10:
        return _blocked(symbol, "stop_run", f"스탑런 이벤트 {len(events)}건뿐 — 최소 표본 미달", write_report)

    order, buy, sell, last_price = _footprint_buckets(deltas)
    closes = [last_price[b] for b in order]
    notional = closes[-1] * NOTIONAL_MULTIPLIER.get(symbol, 20.0)
    cost_bps = ib_futures_effective_cost_bps(symbol, notional)

    import random as _random
    rng = _random.Random(seed)

    horizons: dict[str, dict] = {}
    for hold in hold_buckets_list:
        precomputed = []
        for ev in events:
            idx = ev["idx"]
            exit_idx = min(idx + hold, len(closes) - 1)
            entry_px, exit_px = closes[idx], closes[exit_idx]
            cost = (abs(entry_px) + abs(exit_px)) * trade_size * cost_bps / 10_000.0
            side_sign = 1.0 if ev["side"] == "buy" else -1.0
            precomputed.append((side_sign, entry_px, exit_px, cost))

        actual_pnls = [sign * (ex - en) * trade_size - c for sign, en, ex, c in precomputed]
        strat = trade_metrics([{"pnl": pnl} for pnl in actual_pnls])

        random_totals = []
        for _ in range(n_runs):
            total = 0.0
            for _sign, en, ex, c in precomputed:
                rsign = rng.choice((1.0, -1.0))
                total += rsign * (ex - en) * trade_size - c
            random_totals.append(round(total, 6))
        pval = empirical_p_value(strat["total_pnl"], random_totals)
        horizons[f"{hold}b"] = {"strategy": strat, "random": pval}

    result = {"symbol": symbol, "signal": "stop_run", "blocked": False,
              "n_events": len(events), "horizons": horizons}
    if write_report:
        for h_key, h_res in horizons.items():
            rep = build_report(
                name=f"orderflow_futures_stop_run_{symbol}_{h_key}",
                hypothesis=f"스탑런 이벤트 방향 즉시추종, {h_key} 고정청산",
                universe=[symbol], timeframe="event",
                cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
                strategy=h_res["strategy"], random_pval=h_res["random"],
                naive={"total_pnl": None, "note": "이벤트기반 방향추종 buy&hold 비교 부적합"},
                walk_forward_result={"summary": {}},
                is_harness_dryrun=False,
                extra={"n_events": len(events), "note": "DORMANT hypothesis. NOT validated alpha."},
            )
            h_res["report"] = rep
    return result


def run_all_hypotheses(
    delta_paths_by_symbol: dict[str, list[str]],
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
) -> dict:
    """5신호 x N심볼 전부 실행 -> p-value 모아 BH-FDR 보정. BLOCKED 결과는
    p-value 없어 BH-FDR 입력에서 제외(survivors 배열은 results와 동일 순서 유지,
    BLOCKED 위치는 항상 False)."""
    results: dict[str, dict] = {}
    for symbol, paths in delta_paths_by_symbol.items():
        for signal_name in SIGNAL_BUILDERS:
            key = f"{symbol}:{signal_name}"
            results[key] = run_signal_hypothesis(symbol, signal_name, paths, n_runs=n_runs, seed=seed, write_report=write_report)
        results[f"{symbol}:stop_run"] = run_stop_run_hypothesis(symbol, paths, n_runs=n_runs, seed=seed, write_report=write_report)

    keys = list(results.keys())
    pvals: list[float] = []
    pval_keys: list[str] = []
    for k in keys:
        r = results[k]
        if r.get("blocked"):
            continue
        if "random" in r:
            p = r["random"].get("p_value")
            if p is not None:
                pvals.append(p)
                pval_keys.append(k)
        elif "horizons" in r:
            for h_key, h_res in r["horizons"].items():
                p = h_res["random"].get("p_value")
                if p is not None:
                    pvals.append(p)
                    pval_keys.append(f"{k}:{h_key}")

    from research.validation.multiple_testing import benjamini_hochberg
    bh = benjamini_hochberg(pvals, alpha=0.1)
    bh["keys"] = pval_keys
    return {"results": results, "bh_fdr": bh}


def _blocked(symbol: str, signal_name: str, msg: str, write_report: bool) -> dict:
    res = {"symbol": symbol, "signal": signal_name, "blocked": True, "reason": msg,
           "verdict": "BLOCKED: " + msg}
    if write_report:
        import json
        import os
        from research.reports.alpha_report import REPORT_DIR
        os.makedirs(REPORT_DIR, exist_ok=True)
        base = os.path.join(REPORT_DIR, f"orderflow_futures_{signal_name}_{symbol}")
        with open(base + ".json", "w") as f:
            json.dump(res, f, indent=2)
        with open(base + ".md", "w") as f:
            f.write(f"# Orderflow Futures {signal_name} — {symbol}\n\n**BLOCKED.** {msg}\n")
    return res
