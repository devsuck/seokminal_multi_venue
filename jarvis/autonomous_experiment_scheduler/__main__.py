"""`python -m jarvis.autonomous_experiment_scheduler <cmd>` — 자율 실험 스케줄러 CLI. **스케줄·기록 전용.**

  schedule   --name [--mandate]                        스케줄/큐 등록 [--commit]
  request    --schedule --experiment [--note]          실험 요청(REQUESTED) [--commit]
  priority   --request --priority [--rule]             우선순위 배정 [--commit]
  policy     --schedule --name [--rule]                스케줄링 정책 [--commit]
  depend     --request --on                            의존 등록 [--commit]
  advance    --request --to                            상태 전이 [--commit]
  plan       --schedule                                실행 계획(위상+우선순위) [--commit]
  report     --schedule / requests [--schedule] / verify / replay / summary

실제 실험 실행 없음 — 스케줄·기록만. SCHEDULE ≠ EXECUTION · PLAN ≠ RUN · PRIORITY ≠ APPROVAL.
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
    from jarvis.autonomous_experiment_scheduler.engine import AutonomousExperimentSchedulerEngine
    return AutonomousExperimentSchedulerEngine()


def _cmd_schedule(a) -> int:
    _p({"committed": a.commit,
        "schedule": _eng().create_schedule(a.name, a.mandate or "", _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_request(a) -> int:
    _p({"committed": a.commit,
        "request": _eng().register_experiment_request(a.schedule, a.experiment, a.note or "",
                                                      _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_priority(a) -> int:
    _p({"committed": a.commit,
        "priority": _eng().assign_priority(a.request, a.priority, a.rule or "", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_policy(a) -> int:
    _p({"committed": a.commit,
        "policy": _eng().create_scheduling_policy(a.schedule, a.name, a.rule or "", _now(),
                                                 commit=a.commit).to_dict()})
    return 0


def _cmd_depend(a) -> int:
    deps = _eng().resolve_dependencies(a.request, [a.on], _now(), commit=a.commit)
    _p({"committed": a.commit, "dependencies": [d.to_dict() for d in deps]})
    return 0


def _cmd_advance(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().update_schedule_state(a.request, a.to, "", _now(),
                                              commit=a.commit).to_dict()})
    return 0


def _cmd_plan(a) -> int:
    _p({"committed": a.commit,
        "plan": _eng().build_execution_plan(a.schedule, "SCHEDULABLE", _now(),
                                            commit=a.commit).to_dict(),
        "note": "PLAN ≠ RUN — no execution"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_schedule_report(a.schedule, "ALL", _now(),
                                                  commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_requests(a) -> int:
    eng = _eng()
    rs = eng.list_requests(a.schedule or "")
    _p({"requests": [{"request_id": r, "state": eng.current_state(r)} for r in rs]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.autonomous_experiment_scheduler.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.autonomous_experiment_scheduler.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.autonomous_experiment_scheduler")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("schedule")
    sc.add_argument("--name", required=True)
    sc.add_argument("--mandate", default="")
    sc.add_argument("--commit", action="store_true")

    rq = sub.add_parser("request")
    rq.add_argument("--schedule", required=True)
    rq.add_argument("--experiment", required=True)
    rq.add_argument("--note", default="")
    rq.add_argument("--commit", action="store_true")

    pr = sub.add_parser("priority")
    pr.add_argument("--request", required=True)
    pr.add_argument("--priority", type=int, required=True)
    pr.add_argument("--rule", default="")
    pr.add_argument("--commit", action="store_true")

    po = sub.add_parser("policy")
    po.add_argument("--schedule", required=True)
    po.add_argument("--name", required=True)
    po.add_argument("--rule", default="")
    po.add_argument("--commit", action="store_true")

    de = sub.add_parser("depend")
    de.add_argument("--request", required=True)
    de.add_argument("--on", required=True)
    de.add_argument("--commit", action="store_true")

    ad = sub.add_parser("advance")
    ad.add_argument("--request", required=True)
    ad.add_argument("--to", required=True)
    ad.add_argument("--commit", action="store_true")

    pl = sub.add_parser("plan")
    pl.add_argument("--schedule", required=True)
    pl.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--schedule", required=True)
    rp.add_argument("--commit", action="store_true")

    rs = sub.add_parser("requests")
    rs.add_argument("--schedule", default="")

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"schedule": _cmd_schedule, "request": _cmd_request, "priority": _cmd_priority,
            "policy": _cmd_policy, "depend": _cmd_depend, "advance": _cmd_advance,
            "plan": _cmd_plan, "report": _cmd_report, "requests": _cmd_requests,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
