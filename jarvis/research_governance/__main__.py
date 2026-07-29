"""`python -m jarvis.research_governance <cmd>` — 전략 연구 거버넌스 CLI. **연구 관리 전용.**

  strategy   --strategy-id --name --author --asset-class [--description] [--commit]
  experiment --strategy-id --version --hypothesis [--dataset-version ...] [--commit]
  backtest   --experiment-id --sharpe --return --volatility --max-drawdown --turnover [--commit]
  validate   --experiment-id [--oos] [--wf] [--cost-ok] [--robust] [--beats-bench] [--overfit] [--commit]
  compare    --experiment-a --experiment-b [--commit]
  report / verify / summary / replay

주문/실행/자본배분/live trading/자동승인 없음 — 연구 기록·분석만. VALIDATED≠trading permission.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _eng():
    from jarvis.research_governance.engine import ResearchGovernanceEngine
    return ResearchGovernanceEngine()


def _cmd_strategy(a) -> int:
    eng = _eng()
    s = eng.register_strategy(a.strategy_id, a.name, a.description or "", a.author,
                              a.asset_class, _now(), commit=a.commit)
    if a.version:
        eng.create_version(a.strategy_id, a.version, a.author, {}, now=_now(), commit=a.commit)
    _p({"committed": a.commit, "strategy": s.to_dict()})
    return 0


def _cmd_experiment(a) -> int:
    r = _eng().create_experiment(a.strategy_id, a.version, a.hypothesis,
                                 dataset_version=a.dataset_version or "",
                                 feature_version=a.feature_version or "",
                                 model_version=a.model_version or "",
                                 backtest_period=a.period or "", benchmark=a.benchmark or "",
                                 now=_now(), commit=a.commit)
    _p({"committed": a.commit, "experiment": r.to_dict()})
    return 0


def _cmd_backtest(a) -> int:
    r = _eng().record_backtest(a.experiment_id, total_return=a.total_return, volatility=a.volatility,
                               sharpe=a.sharpe, max_drawdown=a.max_drawdown, turnover=a.turnover,
                               now=_now(), commit=a.commit)
    _p({"committed": a.commit, "backtest": r.to_dict()})
    return 0


def _cmd_validate(a) -> int:
    checks = {"out_of_sample_pass": a.oos, "walk_forward_pass": a.wf,
              "cost_sensitivity_pass": a.cost_ok, "parameter_robustness_pass": a.robust,
              "benchmark_outperforms": a.beats_bench, "overfitting_warning": a.overfit}
    r = _eng().record_validation(a.experiment_id, checks, _now(), commit=a.commit)
    _p({"committed": a.commit, "validation": r.to_dict(),
        "note": "VALIDATED 는 연구 결과 상태 — trading permission 아님"})
    return 0


def _cmd_compare(a) -> int:
    r = _eng().compare_experiments(a.experiment_a, a.experiment_b, _now(), commit=a.commit)
    _p({"committed": a.commit, "comparison": r.to_dict(), "note": "추천 기록만 — 자동 선택 아님"})
    return 0


def _cmd_report(a) -> int:
    _p(_eng().generate_research_report(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_governance.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    return _cmd_report(a)


def _cmd_replay(a) -> int:
    from jarvis.research_governance.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_governance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("strategy")
    for f in ("strategy-id", "name", "author", "asset-class"):
        s.add_argument(f"--{f}", required=True)
    s.add_argument("--description", default="")
    s.add_argument("--version", default="")
    s.add_argument("--commit", action="store_true")
    e = sub.add_parser("experiment")
    for f in ("strategy-id", "version", "hypothesis"):
        e.add_argument(f"--{f}", required=True)
    for f in ("dataset-version", "feature-version", "model-version", "period", "benchmark"):
        e.add_argument(f"--{f}", default="")
    e.add_argument("--commit", action="store_true")
    b = sub.add_parser("backtest")
    b.add_argument("--experiment-id", required=True)
    b.add_argument("--total-return", type=float, default=0.0)
    b.add_argument("--volatility", type=float, default=0.0)
    b.add_argument("--sharpe", type=float, default=0.0)
    b.add_argument("--max-drawdown", type=float, default=0.0)
    b.add_argument("--turnover", type=float, default=0.0)
    b.add_argument("--commit", action="store_true")
    v = sub.add_parser("validate")
    v.add_argument("--experiment-id", required=True)
    v.add_argument("--oos", action="store_true")
    v.add_argument("--wf", action="store_true")
    v.add_argument("--cost-ok", action="store_true")
    v.add_argument("--robust", action="store_true")
    v.add_argument("--beats-bench", action="store_true")
    v.add_argument("--overfit", action="store_true")
    v.add_argument("--commit", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("--experiment-a", required=True)
    c.add_argument("--experiment-b", required=True)
    c.add_argument("--commit", action="store_true")
    sub.add_parser("report")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"strategy": _cmd_strategy, "experiment": _cmd_experiment, "backtest": _cmd_backtest,
            "validate": _cmd_validate, "compare": _cmd_compare, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
