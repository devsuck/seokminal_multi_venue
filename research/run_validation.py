"""알파 검증 하네스 드라이런.

일봉 ema_cross를 기니피그로 전 검증 파이프라인 실행 → 리포트 생성.
⚠️ 목적 = 검증 엔진 동작 확인(드라이런). 알파 주장 아님.

실행:
  PYTHONPATH=. python3 research/run_validation.py
분봉 데이터 생기면 signal_fn만 ORB로 바꿔 그대로 재사용."""
from __future__ import annotations

from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.model.identifiers import InstrumentId
from adapters.data_provider import bar_type_for
from backtest_runner.simple_runner import _ema_signals

from research.validation.cost_model import effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics
from research.validation.baselines import (
    random_same_frequency, naive_buy_hold, empirical_p_value,
)
from research.validation.walk_forward import walk_forward
from research.reports.alpha_report import build_report

CATALOG = "./catalog"
UNIVERSE = ["AAPL.NASDAQ", "MSFT.NASDAQ", "SPY.ARCA"]
FAST, SLOW = 12, 26
TRADE_SIZE = 10.0
N_RUNS = 500
SEED = 42


def load_closes(iid: str) -> list[float]:
    c = ParquetDataCatalog(CATALOG)
    bt = str(bar_type_for(InstrumentId.from_str(iid)))
    bars = sorted(c.bars(bar_types=[bt]), key=lambda b: b.ts_event)
    return [float(b.close) for b in bars]


def run_one(iid: str, cost: dict) -> dict:
    closes = load_closes(iid)
    eff = cost["effective_bps"]

    # 전략: ema_cross
    sigs = _ema_signals(closes, FAST, SLOW)
    trades = simulate_long_short(closes, sigs, TRADE_SIZE, eff)
    strat = trade_metrics(trades)

    # holding 분포 (같은 horizon 유지용)
    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [5]

    # 랜덤 same-frequency 분포 → total PnL 기준 퍼센타일/p
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=TRADE_SIZE, cost_bps=eff, eligible_indices=None,
        n_runs=N_RUNS, seed=SEED,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)

    naive = naive_buy_hold(closes, TRADE_SIZE, eff)
    wf = walk_forward(closes, lambda seg: _ema_signals(seg, FAST, SLOW),
                      n_windows=5, trade_size=TRADE_SIZE, cost_bps=eff)

    rep = build_report(
        name=f"ema_cross_{iid}",
        hypothesis="EMA(12/26) 크로스 — 하네스 드라이런 기니피그(알파 아님)",
        universe=[iid], timeframe="1d (daily)",
        cost=cost, strategy=strat, random_pval=pval, naive=naive,
        walk_forward_result=wf, is_harness_dryrun=True,
        extra={"note": "random baseline은 long-only, 전략은 long/short — 방향 비대칭 있음"},
    )
    return {"iid": iid, "strat": strat, "pval": pval, "naive": naive,
            "wf": wf["summary"], "verdict": rep["verdict"], "md": rep["md_path"]}


def main():
    cost_bps, slip, spread = 1.0, 2.0, 4.0
    eff = effective_cost_bps(cost_bps, slip, spread)
    cost = {"cost_bps": cost_bps, "slippage_bps": slip, "spread_bps": spread, "effective_bps": eff}

    print("=" * 74)
    print("ALPHA VALIDATION HARNESS — DRY RUN (daily ema_cross). NOT AN ALPHA CLAIM.")
    print(f"effective cost/체결: {eff} bps | random runs: {N_RUNS} | seed: {SEED}")
    print("=" * 74)
    for iid in UNIVERSE:
        r = run_one(iid, cost)
        s, p = r["strat"], r["pval"]
        up = " ⚠️UNDERPOWERED" if s["underpowered"] else ""
        print(f"\n### {iid}{up}")
        print(f"  strategy: trades={s['num_trades']} pnl={s['total_pnl']} "
              f"exp={s['expectancy']} PF={s['profit_factor']} win={s['win_rate']}")
        print(f"  vs random: percentile={p['percentile']} p={p['p_value']} "
              f"(random median={p['random_median']}, beating={p['random_beating']}/{p['n_random']})")
        print(f"  naive B&H pnl: {r['naive']['total_pnl']}")
        print(f"  walk-forward: consistency={r['wf']['consistency']} "
              f"avg_pnl={r['wf']['avg_total_pnl']}")
        print(f"  VERDICT: {r['verdict']}")
        print(f"  report: {r['md']}")


if __name__ == "__main__":
    main()
