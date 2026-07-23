"""`python -m jarvis.simulation_environment <cmd>` — 연구 시뮬레이션 CLI. **비실행 분석 전용.**

  scenario --name --type [--description] [--commit]
  run      --candidate --scenario-id [--params-json --dataset --seed] [--commit]
  result   --run-id [--metrics-json] [--commit]     # metrics 없으면 결정적 파생
  compare  --run-a --run-b [--commit]
  report / verify / summary / replay

실제 order/trade/portfolio 변경/capital allocation/live trading 없음 — 재현·비교·기록만.
결과는 결정적 평가값 · score ≠ selection · result ≠ deployment.
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
    from jarvis.simulation_environment.engine import ResearchSimulationEngine
    return ResearchSimulationEngine()


def _cmd_scenario(a) -> int:
    s = _eng().register_scenario(a.name, a.type, a.description or "", {}, _now(), commit=a.commit)
    _p({"committed": a.commit, "scenario": s.to_dict(), "note": "분석 시나리오 — 실행 아님"})
    return 0


def _cmd_run(a) -> int:
    params = json.loads(a.params_json) if a.params_json else {}
    r = _eng().create_simulation(a.candidate, a.scenario_id, params, a.dataset or "",
                                 a.seed or "0", _now(), commit=a.commit)
    _p({"committed": a.commit, "run": r.to_dict(), "note": "시뮬레이션 런 — 실제 실행 아님"})
    return 0


def _cmd_result(a) -> int:
    eng = _eng()
    if a.metrics_json:
        res = eng.record_result(a.run_id, json.loads(a.metrics_json), _now(), commit=a.commit)
    else:
        res = eng.run_simulation_record(a.run_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "result": res.to_dict(), "note": "결정적 평가값 — 자동 판단 없음"})
    return 0


def _cmd_compare(a) -> int:
    c = _eng().compare_results(a.run_a, a.run_b, _now(), commit=a.commit)
    _p({"committed": a.commit, "comparison": c.to_dict(), "note": "자동 추천 없음 — 사람 검토"})
    return 0


def _cmd_report(a) -> int:
    _p(_eng().generate_report(_now(), commit=getattr(a, "commit", False)).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.simulation_environment.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.simulation_environment.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.simulation_environment")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scenario")
    sc.add_argument("--name", required=True)
    sc.add_argument("--type", required=True)
    sc.add_argument("--description", default="")
    sc.add_argument("--commit", action="store_true")
    rn = sub.add_parser("run")
    rn.add_argument("--candidate", required=True)
    rn.add_argument("--scenario-id", required=True)
    rn.add_argument("--params-json", default="")
    rn.add_argument("--dataset", default="")
    rn.add_argument("--seed", default="0")
    rn.add_argument("--commit", action="store_true")
    rs = sub.add_parser("result")
    rs.add_argument("--run-id", required=True)
    rs.add_argument("--metrics-json", default="")
    rs.add_argument("--commit", action="store_true")
    cm = sub.add_parser("compare")
    cm.add_argument("--run-a", required=True)
    cm.add_argument("--run-b", required=True)
    cm.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("summary")
    sub.add_parser("verify")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"scenario": _cmd_scenario, "run": _cmd_run, "result": _cmd_result,
            "compare": _cmd_compare, "report": _cmd_report, "summary": _cmd_report,
            "verify": _cmd_verify, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
