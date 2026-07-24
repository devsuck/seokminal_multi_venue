"""`python -m jarvis.experiment_orchestration <cmd>` — 실험 조정 CLI. **실험 실행 없음.**

  plan       --name [--objective]                          실험 계획(DRAFT) [--commit]
  schedule   --plan [--for --priority --window]            스케줄(→SCHEDULED) [--commit]
  dependency --plan --depends-on [--type]                  의존성(순환 방지) [--commit]
  request    --plan --requester                            실행 요청(REQUESTED, 실행 없음) [--commit]
  approve    --request --approver                          요청 승인(사람 필수, 실행 없음) [--commit]
  history    --plan --phase [--outcome --detail]           실험 이력 [--commit]
  report [--scope] / verify / summary / replay

실험 실행·거래·배포·자동 승인 없음. ORCHESTRATION ≠ EXECUTION · APPROVED ≠ EXECUTED.
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
    from jarvis.experiment_orchestration.engine import ExperimentOrchestrationEngine
    return ExperimentOrchestrationEngine()


def _cmd_plan(a) -> int:
    _p({"committed": a.commit,
        "plan": _eng().create_plan(a.name, a.objective or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_schedule(a) -> int:
    _p({"committed": a.commit,
        "schedule": _eng().schedule_plan(a.plan, a.__dict__.get("for") or "", a.priority or "NORMAL",
                                       a.window or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_dependency(a) -> int:
    _p({"committed": a.commit,
        "dependency": _eng().add_dependency(a.plan, a.depends_on, a.type or "SEQUENTIAL", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_request(a) -> int:
    _p({"committed": a.commit,
        "request": _eng().create_execution_request(a.plan, a.requester, _now(),
                                                  commit=a.commit).to_dict(),
        "note": "is_executed=False · human approval required"})
    return 0


def _cmd_approve(a) -> int:
    _p({"committed": a.commit,
        "request": _eng().approve_request(a.request, a.approver, "approved", _now(),
                                        commit=a.commit).to_dict(),
        "note": "APPROVED ≠ EXECUTED"})
    return 0


def _cmd_history(a) -> int:
    _p({"committed": a.commit,
        "history": _eng().record_history(a.plan, a.phase, a.outcome or "RECORDED", a.detail or "",
                                       _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.experiment_orchestration.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.experiment_orchestration.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.experiment_orchestration")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan")
    pl.add_argument("--name", required=True)
    pl.add_argument("--objective", default="")
    pl.add_argument("--commit", action="store_true")

    sc = sub.add_parser("schedule")
    sc.add_argument("--plan", required=True)
    sc.add_argument("--for", default="")
    sc.add_argument("--priority", default="NORMAL")
    sc.add_argument("--window", default="")
    sc.add_argument("--commit", action="store_true")

    de = sub.add_parser("dependency")
    de.add_argument("--plan", required=True)
    de.add_argument("--depends-on", dest="depends_on", required=True)
    de.add_argument("--type", default="SEQUENTIAL")
    de.add_argument("--commit", action="store_true")

    rq = sub.add_parser("request")
    rq.add_argument("--plan", required=True)
    rq.add_argument("--requester", required=True)
    rq.add_argument("--commit", action="store_true")

    ap2 = sub.add_parser("approve")
    ap2.add_argument("--request", required=True)
    ap2.add_argument("--approver", required=True)
    ap2.add_argument("--commit", action="store_true")

    hi = sub.add_parser("history")
    hi.add_argument("--plan", required=True)
    hi.add_argument("--phase", required=True)
    hi.add_argument("--outcome", default="RECORDED")
    hi.add_argument("--detail", default="")
    hi.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"plan": _cmd_plan, "schedule": _cmd_schedule, "dependency": _cmd_dependency,
            "request": _cmd_request, "approve": _cmd_approve, "history": _cmd_history,
            "report": _cmd_report, "verify": _cmd_verify, "summary": _cmd_summary,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
