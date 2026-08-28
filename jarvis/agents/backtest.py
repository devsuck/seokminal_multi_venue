"""Backtest Runner Agent — 결정적 하네스 실행(기존 research 하네스 래핑).

AI는 spec(DSL) 제출. 실행은 결정적 파이썬. 결과는 불변 + provenance 연결:
data_version·code_version·config_hash·random_seed·timestamp.
registry 전이: data_audit_passed→backtested.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from jarvis.agents import BACKTEST_AGENT
from jarvis.config import CODE_VERSION
from jarvis.permissions import require
from jarvis.registry import Status, StrategyRegistry, config_hash


def run(strategy_id: str, spec: dict | None = None, commit: bool = True) -> dict:
    """spec 있으면 합성 하네스, 없으면 기존 experiment_registry 결과 리플레이(불변)."""
    require(BACKTEST_AGENT, "run_backtest", strategy_id)
    seed = int((spec or {}).get("seed", 42))

    if spec and "edge_bps" in spec:
        from research.lab.evaluator import evaluate_synthetic
        from research.lab.hypotheses import Hypothesis
        h = Hypothesis(id=strategy_id, name=spec.get("name", strategy_id), family=spec.get("family", "event"),
                       market=spec.get("market", "KR"), thesis="", kill="", entry="", hold="",
                       universe="", cost_bps=float(spec.get("cost_bps", 40.0)), data_mode="synthetic_demo",
                       n_trades=int(spec.get("n_trades", 40)), holding=[int(spec.get("hold", 20))],
                       edge_bps=float(spec["edge_bps"]), seed=seed)
        r = evaluate_synthetic(h)
        metrics = {"net": (r["backtest"] or {}).get("strategy_net"),
                   "random_percentile": (r["random"] or {}).get("percentile"),
                   "empirical_p": (r["random"] or {}).get("p_value"),
                   "wf_first": (r["walk_forward"] or {}).get("first"),
                   "wf_second": (r["walk_forward"] or {}).get("second"),
                   "powered": r["powered"]}
        data_version = "synthetic_demo"
    else:
        from research.agents.experiment_registry import already_tested
        rows = already_tested(strategy_id)
        e = rows[-1] if rows else {}
        # net_pnl/random_pct는 소수(2건) legacy 필드명 — 실제 다수(4500+건) 컨벤션은
        # net/percentile(research/autoresearch/engine.py log_experiment 기준). 다수 쪽을
        # 우선하고 legacy로 폴백(2026-08-26: 이 순서가 뒤바뀌어 있어 net이 항상 None으로
        # 리플레이되고 critic이 자동 rejected 처리하던 버그).
        metrics = {"net": e.get("net", e.get("net_pnl")), "random_percentile": e.get("percentile", e.get("random_pct")),
                   "empirical_p": e.get("p"), "wf_first": e.get("wf_first"),
                   "wf_second": e.get("wf_second"), "powered": True,
                   "sharpe": e.get("sharpe"), "ann_return": e.get("ann_return")}
        data_version = str(e.get("data_quality", "unknown"))

    result = {
        "strategy_id": strategy_id, "metrics": metrics,
        "provenance": {"data_version": data_version, "code_version": CODE_VERSION,
                       "config_hash": config_hash(spec or {"strategy_id": strategy_id}),
                       "random_seed": seed,
                       "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "immutable": True,
    }
    if commit:
        reg = StrategyRegistry()
        st = reg.state(strategy_id)
        if st and st["status"] == Status.DATA_AUDIT_PASSED.value:
            reg.transition(strategy_id, Status.BACKTESTED, "backtest_run", evidence=metrics)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.agents.backtest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--strategy", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        print(json.dumps(run(args.strategy, commit=False), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
