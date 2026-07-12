"""BTC/ETH(HL) 원시 틱에 orderflow_futures.py의 6신호 로직 재적용 — 일회성 확인용.

NQ/MNQ 수집기는 footprint_delta(60s 버킷 합산)만 저장하지만 HL 틱 수집기
(`research/run_hl_orderflow_tick_collect.py`)는 개별 체결(`{ts, price, size, side}`)만
저장하고 오더북 스냅샷은 전혀 남기지 않는다. 그래서:
- footprint_imbalance/absorption/cvd_divergence/stop_run: OrderflowAggregator.on_trade()로
  틱을 footprint_delta로 변환하면 그대로 재사용 가능(수집기와 동일 버킷팅 로직).
- wall_proximity/iceberg_refill: heatmap_delta가 필요한데 원본 데이터에 없음 -> 항상 BLOCKED.

비용모델은 IB 선물이 아니라 HL perp(`hl_effective_cost_bps`)를 쓴다 — 자산이 다르므로
당연히 orderflow_futures.py의 심볼별 NOTIONAL_MULTIPLIER/IB 커미션은 쓰지 않는다.

⚠️ DORMANT 확인용 스크립트. 결과는 통계적 스크리닝일 뿐 실집행 근거 아님.
"""
from __future__ import annotations

import glob
import json

from orderflow.aggregator import OrderflowAggregator
from orderflow.models import TradeEvent
from research.hypotheses.orderflow_context_gate import build_confluence_signals, build_gated_confluence_signals
from research.hypotheses.orderflow_futures import SIGNAL_BUILDERS, stop_run_events
from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.cost_model import hl_effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/hl_orderflow_tick"
TRADE_SIZE = 1.0
N_RUNS = 500
SEED = 42
COST_BPS = hl_effective_cost_bps("major", taker=True)


def load_raw_ticks(paths: list[str]) -> list[dict]:
    """원시 틱 jsonl들을 시간순 병합. build_gated_confluence_signals의 바 빌더 입력용
    (footprint_delta로 버킷 합산하기 전, 개별 체결 {ts,price,size,side} 그대로)."""
    ticks = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def ticks_to_footprint_deltas(ticks: list[dict], symbol: str) -> list[dict]:
    """원시 틱(이미 로드된 것) -> OrderflowAggregator.on_trade()로 footprint_delta 스트림 생성.

    라이브 수집기(run_ib_orderflow_tick_collect.py)와 동일하게 Aggregator를
    단일 소스로 재사용 — 버킷팅 로직을 여기서 새로 짜지 않는다."""
    agg = OrderflowAggregator()
    deltas = []
    for t in ticks:
        ev = TradeEvent(symbol=symbol, ts=t["ts"], price=t["price"], size=t["size"], side=t["side"])
        deltas.append(agg.on_trade(ev))
    return deltas


def run_bar_signal(symbol: str, signal_name: str, deltas: list[dict]) -> dict:
    if signal_name == "confluence":
        data = build_confluence_signals(deltas)
    else:
        data = SIGNAL_BUILDERS[signal_name](deltas)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < 10:
        return {"symbol": symbol, "signal": signal_name, "blocked": True,
                "reason": f"{len(closes)}봉뿐 — 최소 표본 미달"}

    trades = simulate_long_short(closes, signals, TRADE_SIZE, COST_BPS)
    strat = trade_metrics(trades)
    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=TRADE_SIZE, cost_bps=COST_BPS,
        eligible_indices=eligible, n_runs=N_RUNS, seed=SEED,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)
    return {"symbol": symbol, "signal": signal_name, "blocked": False,
            "strategy": strat, "random": pval, "n_bars": len(closes), "eligible_count": len(eligible)}


def run_stop_run(symbol: str, deltas: list[dict]) -> dict:
    events = stop_run_events(deltas)
    if len(events) < 10:
        return {"symbol": symbol, "signal": "stop_run", "blocked": True,
                "reason": f"이벤트 {len(events)}건뿐 — 최소 표본 미달"}

    from research.hypotheses.orderflow_futures import _footprint_buckets
    order, _buy, _sell, _open_price, last_price = _footprint_buckets(deltas)
    closes = [last_price[b] for b in order]

    import random as _random
    rng = _random.Random(SEED)
    horizons: dict[str, dict] = {}
    for hold in (1, 3, 5):
        precomputed = []
        for ev in events:
            idx = ev["idx"]
            exit_idx = min(idx + hold, len(closes) - 1)
            entry_px, exit_px = closes[idx], closes[exit_idx]
            cost = (abs(entry_px) + abs(exit_px)) * TRADE_SIZE * COST_BPS / 10_000.0
            side_sign = 1.0 if ev["side"] == "buy" else -1.0
            precomputed.append((side_sign, entry_px, exit_px, cost))

        actual_pnls = [sign * (ex - en) * TRADE_SIZE - c for sign, en, ex, c in precomputed]
        strat = trade_metrics([{"pnl": pnl} for pnl in actual_pnls])

        random_totals = []
        for _ in range(N_RUNS):
            total = 0.0
            for _sign, en, ex, c in precomputed:
                rsign = rng.choice((1.0, -1.0))
                total += rsign * (ex - en) * TRADE_SIZE - c
            random_totals.append(round(total, 6))
        pval = empirical_p_value(strat["total_pnl"], random_totals)
        horizons[f"{hold}b"] = {"strategy": strat, "random": pval}

    return {"symbol": symbol, "signal": "stop_run", "blocked": False,
            "n_events": len(events), "horizons": horizons}


def run_gated_signal(symbol: str, deltas: list[dict], ticks: list[dict]) -> dict:
    data = build_gated_confluence_signals(deltas, ticks)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < 10:
        return {"symbol": symbol, "signal": "gated_confluence", "blocked": True,
                "reason": f"{len(closes)}봉뿐 — 최소 표본 미달"}

    trades = simulate_long_short(closes, signals, TRADE_SIZE, COST_BPS)
    strat = trade_metrics(trades)
    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=TRADE_SIZE, cost_bps=COST_BPS,
        eligible_indices=eligible, n_runs=N_RUNS, seed=SEED,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)
    return {"symbol": symbol, "signal": "gated_confluence", "blocked": False,
            "strategy": strat, "random": pval, "n_bars": len(closes), "eligible_count": len(eligible)}


def main() -> None:
    all_results: list[dict] = []
    pvals: list[float] = []
    pval_keys: list[str] = []

    gated_results: list[dict] = []
    gated_pvals: list[float] = []
    gated_pval_keys: list[str] = []

    for symbol in ("BTC", "ETH"):
        paths = sorted(glob.glob(f"{DATA_DIR}/{symbol}_*.jsonl"))
        if not paths:
            print(f"{symbol}: 데이터 없음, 스킵")
            continue
        ticks = load_raw_ticks(paths)
        deltas = ticks_to_footprint_deltas(ticks, f"{symbol}.HL")

        for signal_name in ("footprint_imbalance", "absorption", "cvd_divergence", "confluence"):
            r = run_bar_signal(symbol, signal_name, deltas)
            all_results.append(r)
            if not r["blocked"]:
                pvals.append(r["random"]["p_value"])
                pval_keys.append(f"{symbol}:{signal_name}")

        r = run_stop_run(symbol, deltas)
        all_results.append(r)
        if not r["blocked"]:
            for h_key, h_res in r["horizons"].items():
                pvals.append(h_res["random"]["p_value"])
                pval_keys.append(f"{symbol}:stop_run:{h_key}")

        for signal_name in ("wall_proximity", "iceberg_refill"):
            all_results.append({"symbol": symbol, "signal": signal_name, "blocked": True,
                                 "reason": "HL 틱 수집기는 heatmap_delta(오더북) 미저장 — 항상 BLOCKED"})

        gr = run_gated_signal(symbol, deltas, ticks)
        gated_results.append(gr)
        if not gr["blocked"]:
            gated_pvals.append(gr["random"]["p_value"])
            gated_pval_keys.append(f"{symbol}:gated_confluence")

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {"survivors": [], "alpha": 0.1}
    bh["keys"] = pval_keys

    gated_bh = benjamini_hochberg(gated_pvals, alpha=0.1) if gated_pvals else {"survivors": [], "alpha": 0.1}
    gated_bh["keys"] = gated_pval_keys

    print(f"\n=== cost_bps(HL major taker) = {COST_BPS} ===\n")
    for r in all_results:
        if r["blocked"]:
            print(f"{r['symbol']}:{r['signal']} -> BLOCKED ({r['reason']})")
            continue
        if "strategy" in r:
            s = r["strategy"]
            print(f"{r['symbol']}:{r['signal']} -> trades={s['num_trades']} "
                  f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:.2f} "
                  f"p_value={r['random']['p_value']:.4f} (n_bars={r['n_bars']}, eligible={r['eligible_count']})")
        elif "horizons" in r:
            for h_key, h_res in r["horizons"].items():
                s = h_res["strategy"]
                print(f"{r['symbol']}:{r['signal']}:{h_key} -> trades={s['num_trades']} "
                      f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:.2f} "
                      f"p_value={h_res['random']['p_value']:.4f} (n_events={r['n_events']})")

    print(f"\n=== BH-FDR (alpha=0.1) ===")
    print(f"keys: {bh['keys']}")
    print(f"survivors: {bh['survivors']}")

    print(f"\n=== 컨텍스트 게이트 신규 가설 (별도 BH-FDR 풀, 이전 배치와 안 섞음) ===\n")
    for r in gated_results:
        if r["blocked"]:
            print(f"{r['symbol']}:{r['signal']} -> BLOCKED ({r['reason']})")
            continue
        s = r["strategy"]
        print(f"{r['symbol']}:{r['signal']} -> trades={s['num_trades']} "
              f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:.2f} "
              f"p_value={r['random']['p_value']:.4f} (n_bars={r['n_bars']}, eligible={r['eligible_count']})")

    print(f"\n=== 컨텍스트 게이트 BH-FDR (alpha=0.1) ===")
    print(f"keys: {gated_bh['keys']}")
    print(f"survivors: {gated_bh['survivors']}")


if __name__ == "__main__":
    main()
