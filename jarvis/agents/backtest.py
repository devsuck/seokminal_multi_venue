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


# ── experiment_registry row → critic metrics ─────────────────────────────────
# experiment_registry.jsonl은 한 스키마가 아니다(작성 시점별로 42종). 통계 필드가
# 러너마다 다른 이름으로 들어와서, 단일 키로 읽으면 조용히 None이 되고 critic이
# 플래그 0개짜리 "이유 없는 rejected"를 낸다(2026-07-13 auto_fac_* 3건이 이 경로로
# 오탈락). 그래서 별칭을 순서대로 훑고, 그래도 없으면 metrics에 None을 남겨
# critic이 metrics_incomplete로 명시 신고하게 한다.
_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "net": ("net", "net_pnl", "net_base", "mean_return"),
    "random_percentile": ("percentile", "random_pct", "random_percentile"),
    "empirical_p": ("p", "empirical_p", "p_value"),
    "wf_first": ("wf_first",),
    "wf_second": ("wf_second",),
    "sharpe": ("sharpe",),
    "ann_return": ("ann_return",),
}


def _first_present(row: dict, names: tuple[str, ...]):
    """별칭 후보를 순서대로 조회 → 첫 non-None 반환. 전부 없으면 None."""
    for name in names:
        value = row.get(name)
        if value is not None:
            return value
    return None


def _metrics_from_experiment_row(row: dict) -> dict:
    """experiment_registry 행을 critic이 읽는 metrics 스키마로 정규화."""
    metrics = {key: _first_present(row, names) for key, names in _METRIC_ALIASES.items()}
    metrics["powered"] = True
    return metrics


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
        metrics = _metrics_from_experiment_row(e)
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
