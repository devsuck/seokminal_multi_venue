"""`python -m jarvis.research_coordinator <cmd>` — 자율 연구 코디네이터 CLI. **조율·기록 전용.**

  coordinator --name [--mandate]                코디네이터 등록 [--commit]
  plan       --coordinator --name [--objective]  플랜 생성(CREATED) [--commit]
  advance    --plan --to PLANNING|ASSIGNING|RUNNING|BLOCKED|REBALANCING|COMPLETED|ARCHIVED  전이 [--commit]
  assign     --plan --task --owner              태스크 배정 [--commit]
  reassign   --plan --task --owner              태스크 재분배 [--commit]
  progress   --plan --task --percent --state    진행 갱신 [--commit]
  depend     --plan --up --down                 의존성 추가 [--commit]
  schedule   --plan                             스케줄 구성 [--commit]
  blockers   --plan                             정체 탐지 [--commit]
  rebalance  --plan                             워크로드 재분배 [--commit]
  escalate   --plan --task --reason [--severity]  에스컬레이션 [--commit]
  report     --plan                             완료 리포트 [--commit]
  plans / tasks --plan / verify / replay / summary

실제 실행·거래·배포·상위 상태 변경 없음 — 조율·기록만.
COORDINATION ≠ EXECUTION · ASSIGNMENT ≠ TRADE · REBALANCE ≠ DEPLOYMENT · REPORT ≠ APPROVAL.
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
    from jarvis.research_coordinator.engine import ResearchCoordinatorEngine
    return ResearchCoordinatorEngine()


def _cmd_coordinator(a) -> int:
    c = _eng().register_coordinator(a.name, a.mandate or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "coordinator": c.to_dict()})
    return 0


def _cmd_plan(a) -> int:
    p = _eng().create_plan(a.coordinator, a.name, a.objective or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "plan": p.to_dict()})
    return 0


def _cmd_advance(a) -> int:
    e = _eng()
    fn = {"PLANNING": e.start_planning, "ASSIGNING": e.start_assigning, "RUNNING": e.start_running,
          "BLOCKED": e.mark_blocked, "REBALANCING": e.start_rebalancing,
          "COMPLETED": e.complete_plan, "ARCHIVED": e.archive_plan}[a.to]
    _p({"committed": a.commit, "plan": fn(a.plan, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_assign(a) -> int:
    r = _eng().assign_task(a.plan, a.task, a.owner, _now(), commit=a.commit)
    _p({"committed": a.commit, "assignment": r.to_dict()})
    return 0


def _cmd_reassign(a) -> int:
    r = _eng().reassign_task(a.plan, a.task, a.owner, _now(), commit=a.commit)
    _p({"committed": a.commit, "assignment": r.to_dict()})
    return 0


def _cmd_progress(a) -> int:
    r = _eng().update_progress(a.plan, a.task, a.percent, a.state, a.note or "", _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "progress": r.to_dict()})
    return 0


def _cmd_depend(a) -> int:
    r = _eng().add_dependency(a.plan, a.up, a.down, _now(), commit=a.commit)
    _p({"committed": a.commit, "dependency": r.to_dict()})
    return 0


def _cmd_schedule(a) -> int:
    r = _eng().build_schedule(a.plan, _now(), commit=a.commit)
    _p({"committed": a.commit, "schedule": r.to_dict()})
    return 0


def _cmd_blockers(a) -> int:
    _p(_eng().detect_blocker(a.plan, _now(), commit=a.commit))
    return 0


def _cmd_rebalance(a) -> int:
    r = _eng().rebalance_workload(a.plan, _now(), commit=a.commit)
    _p({"committed": a.commit, "workload": r.to_dict(), "note": "REBALANCE ≠ DEPLOYMENT"})
    return 0


def _cmd_escalate(a) -> int:
    r = _eng().escalate_issue(a.plan, a.task or "", a.reason, a.severity or "WARNING", _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "escalation": r.to_dict()})
    return 0


def _cmd_report(a) -> int:
    r = _eng().generate_report(a.plan, "PLAN", _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "note": "is_binding=False"})
    return 0


def _cmd_plans(a) -> int:
    _p({"plans": _eng().list_plans(a.coordinator or "")})
    return 0


def _cmd_tasks(a) -> int:
    _p({"tasks": _eng().list_tasks(a.plan)})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_coordinator.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_coordinator.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_coordinator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    co = sub.add_parser("coordinator")
    co.add_argument("--name", required=True)
    co.add_argument("--mandate", default="")
    co.add_argument("--commit", action="store_true")
    pl = sub.add_parser("plan")
    pl.add_argument("--coordinator", required=True)
    pl.add_argument("--name", required=True)
    pl.add_argument("--objective", default="")
    pl.add_argument("--commit", action="store_true")
    ad = sub.add_parser("advance")
    ad.add_argument("--plan", required=True)
    ad.add_argument("--to", required=True,
                    choices=["PLANNING", "ASSIGNING", "RUNNING", "BLOCKED", "REBALANCING",
                             "COMPLETED", "ARCHIVED"])
    ad.add_argument("--commit", action="store_true")
    asn = sub.add_parser("assign")
    asn.add_argument("--plan", required=True)
    asn.add_argument("--task", required=True)
    asn.add_argument("--owner", required=True)
    asn.add_argument("--commit", action="store_true")
    ra = sub.add_parser("reassign")
    ra.add_argument("--plan", required=True)
    ra.add_argument("--task", required=True)
    ra.add_argument("--owner", required=True)
    ra.add_argument("--commit", action="store_true")
    pr = sub.add_parser("progress")
    pr.add_argument("--plan", required=True)
    pr.add_argument("--task", required=True)
    pr.add_argument("--percent", type=int, default=0)
    pr.add_argument("--state", required=True,
                    choices=["ASSIGNED", "IN_PROGRESS", "BLOCKED", "COMPLETED"])
    pr.add_argument("--note", default="")
    pr.add_argument("--commit", action="store_true")
    dp = sub.add_parser("depend")
    dp.add_argument("--plan", required=True)
    dp.add_argument("--up", required=True)
    dp.add_argument("--down", required=True)
    dp.add_argument("--commit", action="store_true")
    sc = sub.add_parser("schedule")
    sc.add_argument("--plan", required=True)
    sc.add_argument("--commit", action="store_true")
    bl = sub.add_parser("blockers")
    bl.add_argument("--plan", required=True)
    bl.add_argument("--commit", action="store_true")
    rb = sub.add_parser("rebalance")
    rb.add_argument("--plan", required=True)
    rb.add_argument("--commit", action="store_true")
    es = sub.add_parser("escalate")
    es.add_argument("--plan", required=True)
    es.add_argument("--task", default="")
    es.add_argument("--reason", required=True)
    es.add_argument("--severity", default="WARNING")
    es.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--plan", required=True)
    rp.add_argument("--commit", action="store_true")
    pls = sub.add_parser("plans")
    pls.add_argument("--coordinator", default="")
    tk = sub.add_parser("tasks")
    tk.add_argument("--plan", required=True)
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"coordinator": _cmd_coordinator, "plan": _cmd_plan, "advance": _cmd_advance,
            "assign": _cmd_assign, "reassign": _cmd_reassign, "progress": _cmd_progress,
            "depend": _cmd_depend, "schedule": _cmd_schedule, "blockers": _cmd_blockers,
            "rebalance": _cmd_rebalance, "escalate": _cmd_escalate, "report": _cmd_report,
            "plans": _cmd_plans, "tasks": _cmd_tasks, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
