"""`python -m jarvis.alpha_intelligence <cmd>` — alpha 발견·신호 지능 CLI. **연구 전용.**

  signal     --signal-id --name --author --category [--description] [--version V] [--commit]
  feature    --feature-id --name --source-dataset --formula --calc-version [--commit]
  hypothesis --signal-id --version --statement [--rationale] [--commit]
  experiment --signal-id --version --hypothesis-id [--features a,b] [--dataset-version ...] [--commit]
  evaluate   --experiment-id --sharpe --return --volatility --max-drawdown --turnover [robustness flags] [--commit]
  rank [--commit] / report / verify / summary / replay

trading signal 실행·주문·portfolio·자본배분·자동 선택 없음 — 연구 기록·분석만. VALIDATED≠trading enabled.
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
    from jarvis.alpha_intelligence.engine import AlphaIntelligenceEngine
    return AlphaIntelligenceEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_signal(a) -> int:
    eng = _eng()
    s = eng.register_signal(a.signal_id, a.name, a.description or "", a.author, a.category,
                            _now(), commit=a.commit)
    if a.version:
        eng.create_signal_version(a.signal_id, a.version, a.author, "", {}, [], "", _now(),
                                  commit=a.commit)
    _p({"committed": a.commit, "signal": s.to_dict()})
    return 0


def _cmd_feature(a) -> int:
    f = _eng().register_feature(a.feature_id, a.name, a.description or "", a.source_dataset,
                                a.formula, a.calc_version, _now(), commit=a.commit)
    _p({"committed": a.commit, "feature": f.to_dict()})
    return 0


def _cmd_hypothesis(a) -> int:
    h = _eng().create_hypothesis(a.signal_id, a.version, a.statement, a.rationale or "", _now(),
                                 commit=a.commit)
    _p({"committed": a.commit, "hypothesis": h.to_dict()})
    return 0


def _cmd_experiment(a) -> int:
    r = _eng().create_experiment(a.signal_id, a.version, a.hypothesis_id,
                                 feature_dependencies=_split(a.features),
                                 dataset_version=a.dataset_version or "",
                                 evaluation_period=a.period or "", benchmark=a.benchmark or "",
                                 now=_now(), commit=a.commit)
    _p({"committed": a.commit, "experiment": r.to_dict()})
    return 0


def _cmd_evaluate(a) -> int:
    perf = {"total_return": a.total_return, "volatility": a.volatility, "sharpe": a.sharpe,
            "max_drawdown": a.max_drawdown, "turnover": a.turnover}
    rob = {"out_of_sample_pass": a.oos, "walk_forward_pass": a.wf,
           "parameter_sensitivity_pass": a.param, "market_regime_pass": a.regime,
           "cost_sensitivity_pass": a.cost}
    r = _eng().record_evaluation(a.experiment_id, perf, rob, _now(), commit=a.commit)
    _p({"committed": a.commit, "evaluation": r.to_dict(),
        "note": "verdict 는 연구 평가값 — trading enabled 아님"})
    return 0


def _cmd_rank(a) -> int:
    r = _eng().rank_signals(_now(), commit=a.commit)
    _p({"committed": a.commit, "ranking": r.to_dict(), "note": "연구 랭킹 — 자동 선택/배포 없음"})
    return 0


def _cmd_report(a) -> int:
    _p(_eng().generate_alpha_report(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.alpha_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.alpha_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.alpha_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("signal")
    for f in ("signal-id", "name", "author", "category"):
        s.add_argument(f"--{f}", required=True)
    s.add_argument("--description", default="")
    s.add_argument("--version", default="")
    s.add_argument("--commit", action="store_true")
    f = sub.add_parser("feature")
    for x in ("feature-id", "name", "source-dataset", "formula", "calc-version"):
        f.add_argument(f"--{x}", required=True)
    f.add_argument("--description", default="")
    f.add_argument("--commit", action="store_true")
    h = sub.add_parser("hypothesis")
    for x in ("signal-id", "version", "statement"):
        h.add_argument(f"--{x}", required=True)
    h.add_argument("--rationale", default="")
    h.add_argument("--commit", action="store_true")
    e = sub.add_parser("experiment")
    for x in ("signal-id", "version", "hypothesis-id"):
        e.add_argument(f"--{x}", required=True)
    for x in ("features", "dataset-version", "period", "benchmark"):
        e.add_argument(f"--{x}", default="")
    e.add_argument("--commit", action="store_true")
    v = sub.add_parser("evaluate")
    v.add_argument("--experiment-id", required=True)
    for x in ("total-return", "volatility", "sharpe", "max-drawdown", "turnover"):
        v.add_argument(f"--{x}", type=float, default=0.0)
    v.add_argument("--oos", action="store_true")
    v.add_argument("--wf", action="store_true")
    v.add_argument("--param", action="store_true")
    v.add_argument("--regime", action="store_true")
    v.add_argument("--cost", action="store_true")
    v.add_argument("--commit", action="store_true")
    rk = sub.add_parser("rank")
    rk.add_argument("--commit", action="store_true")
    sub.add_parser("report")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"signal": _cmd_signal, "feature": _cmd_feature, "hypothesis": _cmd_hypothesis,
            "experiment": _cmd_experiment, "evaluate": _cmd_evaluate, "rank": _cmd_rank,
            "report": _cmd_report, "verify": _cmd_verify, "summary": _cmd_report,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
