"""SIGNAL-BUT-SUBCOST 후보(방향예측력 유의, taker net PnL<=0)를 maker 체결 가정으로
재검증 — retrospective 감사에서 BH-FDR 생존한 7개 중: ETH:footprint_imbalance
(taker net_pnl=-3194.56, p=0.0100) + large_trade_event 6개(BTC/ETH x 10/30/60s,
전부 p=0.002=하한선). taker 6.0bps -> maker 3.0bps(hl_effective_cost_bps("major",
taker=False))로 비용만 바꾸고 신호/파라미터는 그대로.

⚠️ 중요 캐비앗: maker 체결은 이상화된 가정이다. 두 신호 다 "이 순간 진입"이 핵심인
반응형 신호(footprint_imbalance=봉마감 즉시, large_trade_event=대량체결 직후) — 실제로
리밋오더가 그 타이밍에 체결됐을지는 별개 문제(체결모델 미검증). 여기 결과는 "비용만
낮아지면 얼마나 회복되는지"의 상한 추정치로 해석할 것, 실집행 가능성 확인 아님.
"""
from __future__ import annotations

import glob

from orderflow.aggregator import OrderflowAggregator
from orderflow.models import TradeEvent
from research.hypotheses.orderflow_futures import SIGNAL_BUILDERS
from research.strategies.orderflow_absorption import run_large_trade_event_hypothesis
from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.cost_model import hl_effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics

DATA_DIR = "research/data/hl_orderflow_tick"
TARGET_NOTIONAL_USD = 1000.0
N_RUNS = 500
SEED = 42

TAKER_BPS = hl_effective_cost_bps("major", taker=True)
MAKER_BPS = hl_effective_cost_bps("major", taker=False)


def load_raw_ticks(paths: list[str]) -> list[dict]:
    import json
    ticks = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def run_footprint_at_cost(symbol: str, deltas: list[dict], cost_bps: float) -> dict:
    data = SIGNAL_BUILDERS["footprint_imbalance"](deltas)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    trade_size = TARGET_NOTIONAL_USD / sorted(closes)[len(closes) // 2]
    trades = simulate_long_short(closes, signals, trade_size, cost_bps)
    strat = trade_metrics(trades)
    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=trade_size, cost_bps=cost_bps,
        eligible_indices=eligible, n_runs=N_RUNS, seed=SEED,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)
    return {"strategy": strat, "random": pval}


def main() -> None:
    print(f"taker={TAKER_BPS}bps  maker={MAKER_BPS}bps\n")

    print("=== footprint_imbalance: taker vs maker ===\n")
    for symbol in ("BTC", "ETH"):
        paths = sorted(glob.glob(f"{DATA_DIR}/{symbol}_*.jsonl"))
        if not paths:
            continue
        ticks = load_raw_ticks(paths)
        agg = OrderflowAggregator()
        deltas = [agg.on_trade(TradeEvent(symbol=f"{symbol}.HL", ts=t["ts"], price=t["price"],
                                           size=t["size"], side=t["side"])) for t in ticks]
        for label, cost in (("taker", TAKER_BPS), ("maker", MAKER_BPS)):
            r = run_footprint_at_cost(symbol, deltas, cost)
            s, rnd = r["strategy"], r["random"]
            print(f"{symbol}:footprint_imbalance:{label:5s} trades={s['num_trades']:5d} "
                  f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:9.2f} "
                  f"p={rnd['p_value']:.4f} pctile={rnd['percentile']:.1f}")
        print()

    print("=== large_trade_event: taker vs maker (6개) ===\n")
    for symbol in ("BTC", "ETH"):
        paths = sorted(glob.glob(f"{DATA_DIR}/{symbol}_*.jsonl"))
        if not paths:
            continue
        for label, taker_flag in (("taker", True), ("maker", False)):
            r = run_large_trade_event_hypothesis(f"{symbol}.HL", paths, n_runs=N_RUNS, seed=SEED,
                                                  write_report=False, taker=taker_flag)
            for h_key, h_res in r["horizons"].items():
                s, rnd = h_res["strategy"], h_res["random"]
                print(f"{symbol}:large_trade_event:{h_key}:{label:5s} trades={s['num_trades']:5d} "
                      f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:9.2f} "
                      f"p={rnd['p_value']:.4f} pctile={rnd['percentile']:.1f}")
        print()


if __name__ == "__main__":
    main()
