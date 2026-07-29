"""`python -m jarvis.experiment_tracking <cmd>` — 실험 추적 CLI. **실행 없음.**

  experiment --name [--objective]                          실험 등록 [--commit]
  run        --experiment [--dataset-version --code-version]  실행 기록 [--commit]
  param      --run --key --value                           파라미터 [--commit]
  result     --run --metric --value                        결과 [--commit]
  compare    --run-a --run-b                               실행 비교 [--commit]
  summary-exp --experiment                                 실험 요약
  report [--scope] / verify / summary / replay

실행·거래·배포·자본 배분 없음. TRACK ≠ EXECUTE · RECORD ≠ RUN.
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
    from jarvis.experiment_tracking.engine import ExperimentTrackingEngine
    return ExperimentTrackingEngine()


def _cmd_experiment(a) -> int:
    _p({"committed": a.commit,
        "experiment": _eng().create_experiment(a.name, a.objective or "", [], _now(),
                                             commit=a.commit).to_dict()})
    return 0


def _cmd_run(a) -> int:
    _p({"committed": a.commit,
        "run": _eng().record_run(a.experiment, a.dataset_version or "", a.code_version or "", "",
                               _now(), commit=a.commit).to_dict(),
        "note": "status=RECORDED · TRACK ≠ EXECUTE"})
    return 0


def _cmd_param(a) -> int:
    _p({"committed": a.commit,
        "parameter": _eng().record_parameter(a.run, a.key, a.value, _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_result(a) -> int:
    _p({"committed": a.commit,
        "result": _eng().record_result(a.run, a.metric, a.value, _now(),
                                      commit=a.commit).to_dict()})
    return 0


def _cmd_compare(a) -> int:
    _p({"committed": a.commit,
        "comparison": _eng().compare_runs(a.run_a, a.run_b, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_summary_exp(a) -> int:
    _p(_eng().generate_summary(a.experiment))
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.experiment_tracking.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.experiment_tracking.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.experiment_tracking")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("experiment")
    ex.add_argument("--name", required=True)
    ex.add_argument("--objective", default="")
    ex.add_argument("--commit", action="store_true")

    ru = sub.add_parser("run")
    ru.add_argument("--experiment", required=True)
    ru.add_argument("--dataset-version", dest="dataset_version", default="")
    ru.add_argument("--code-version", dest="code_version", default="")
    ru.add_argument("--commit", action="store_true")

    pa = sub.add_parser("param")
    pa.add_argument("--run", required=True)
    pa.add_argument("--key", required=True)
    pa.add_argument("--value", required=True)
    pa.add_argument("--commit", action="store_true")

    rs = sub.add_parser("result")
    rs.add_argument("--run", required=True)
    rs.add_argument("--metric", required=True)
    rs.add_argument("--value", type=float, required=True)
    rs.add_argument("--commit", action="store_true")

    cp = sub.add_parser("compare")
    cp.add_argument("--run-a", dest="run_a", required=True)
    cp.add_argument("--run-b", dest="run_b", required=True)
    cp.add_argument("--commit", action="store_true")

    se = sub.add_parser("summary-exp")
    se.add_argument("--experiment", required=True)

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"experiment": _cmd_experiment, "run": _cmd_run, "param": _cmd_param,
            "result": _cmd_result, "compare": _cmd_compare, "summary-exp": _cmd_summary_exp,
            "report": _cmd_report, "verify": _cmd_verify, "summary": _cmd_summary,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
