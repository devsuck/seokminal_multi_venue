"""`python -m jarvis.experiment_manager <cmd>` — 자율 실험 매니저 CLI. **제안 전용.**

  propose  --title --hypothesis --by [--objective]  실험 제안(PROPOSED) [--commit]
  advance  --exp --to REVIEWED|APPROVED_FOR_RESEARCH|COMPLETED  전이 [--commit]
  plan     --exp --method [--dataset --vars a,b --criteria x,y]  실험 계획 [--commit]
  request  --exp [--plan --scope --why]             연구 요청 [--commit]
  results  --exp [--outcome --summary --metrics-json]  결과 수집 [--commit]
  status   --exp                                    상태 추적
  report   --exp                                    실험 리포트 [--commit]
  experiments / verify / replay / summary

실제 라이브 전략 실행·배포 없음 — 제안·계획·연구요청·결과만. 연구 승인 ≠ 거래 승인.
PROPOSAL ≠ EXECUTION · APPROVED_FOR_RESEARCH ≠ TRADING_APPROVAL · RESULT ≠ DEPLOYMENT.
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
    from jarvis.experiment_manager.engine import ExperimentManagerEngine
    return ExperimentManagerEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_propose(a) -> int:
    e = _eng().propose_experiment(a.title, a.hypothesis, a.by, a.objective or "", _now(),
                                  commit=a.commit)
    _p({"committed": a.commit, "experiment": e.to_dict()})
    return 0


def _cmd_advance(a) -> int:
    e = _eng()
    fn = {"REVIEWED": e.review_experiment, "APPROVED_FOR_RESEARCH": e.approve_for_research,
          "COMPLETED": e.complete_experiment}[a.to]
    _p({"committed": a.commit, "experiment": fn(a.exp, "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_plan(a) -> int:
    p = _eng().generate_experiment_plan(a.exp, a.method, _split(a.vars), a.dataset or "",
                                        _split(a.criteria), a.horizon or "", _now(),
                                        commit=a.commit)
    _p({"committed": a.commit, "plan": p.to_dict()})
    return 0


def _cmd_request(a) -> int:
    r = _eng().create_research_request(a.exp, a.plan or "", a.scope or "RESEARCH", a.why or "",
                                       _now(), commit=a.commit)
    _p({"committed": a.commit, "request": r.to_dict(), "note": "APPROVED_FOR_RESEARCH ≠ TRADING_APPROVAL"})
    return 0


def _cmd_results(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().collect_results(a.exp, metrics, _split(a.findings), a.outcome or "PENDING",
                               a.summary or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "result": r.to_dict()})
    return 0


def _cmd_status(a) -> int:
    _p(_eng().track_experiment_status(a.exp))
    return 0


def _cmd_report(a) -> int:
    r = _eng().generate_report(a.exp, "EXPERIMENT", _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_experiments(a) -> int:
    _p({"experiments": _eng().list_experiments()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.experiment_manager.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.experiment_manager.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.experiment_manager")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("propose")
    pr.add_argument("--title", required=True)
    pr.add_argument("--hypothesis", required=True)
    pr.add_argument("--by", required=True)
    pr.add_argument("--objective", default="")
    pr.add_argument("--commit", action="store_true")
    ad = sub.add_parser("advance")
    ad.add_argument("--exp", required=True)
    ad.add_argument("--to", required=True,
                    choices=["REVIEWED", "APPROVED_FOR_RESEARCH", "COMPLETED"])
    ad.add_argument("--commit", action="store_true")
    pl = sub.add_parser("plan")
    pl.add_argument("--exp", required=True)
    pl.add_argument("--method", required=True)
    pl.add_argument("--dataset", default="")
    pl.add_argument("--vars", default="")
    pl.add_argument("--criteria", default="")
    pl.add_argument("--horizon", default="")
    pl.add_argument("--commit", action="store_true")
    rq = sub.add_parser("request")
    rq.add_argument("--exp", required=True)
    rq.add_argument("--plan", default="")
    rq.add_argument("--scope", default="RESEARCH")
    rq.add_argument("--why", default="")
    rq.add_argument("--commit", action="store_true")
    rs = sub.add_parser("results")
    rs.add_argument("--exp", required=True)
    rs.add_argument("--outcome", default="PENDING")
    rs.add_argument("--summary", default="")
    rs.add_argument("--findings", default="")
    rs.add_argument("--metrics-json", default="")
    rs.add_argument("--commit", action="store_true")
    st = sub.add_parser("status")
    st.add_argument("--exp", required=True)
    rp = sub.add_parser("report")
    rp.add_argument("--exp", required=True)
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("experiments")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"propose": _cmd_propose, "advance": _cmd_advance, "plan": _cmd_plan,
            "request": _cmd_request, "results": _cmd_results, "status": _cmd_status,
            "report": _cmd_report, "experiments": _cmd_experiments, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
