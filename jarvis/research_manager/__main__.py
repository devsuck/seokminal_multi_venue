"""`python -m jarvis.research_manager <cmd>` — 자율 연구 관리자 CLI. **계획·추적·모니터링 전용.**

  plan       --name [--objective]                        연구 계획 [--commit]
  task       --plan --name [--desc --owner]              작업(→PLANNED) [--commit]
  depend     --task --on                                 의존 등록 [--commit]
  progress   --task [--percent --status --note]          진행 추적(→RUNNING) [--commit]
  complete   --plan / review --plan / archive --plan     상태 전이 [--commit]
  report     --plan / plans / tasks --plan / order --plan / verify / replay / summary

거래 시작·주문 실행·모델 배포 없음. MANAGE ≠ EXECUTION · PLAN ≠ DEPLOYMENT · TRACK ≠ TRADING.
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
    from jarvis.research_manager.engine import AutonomousResearchManagerEngine
    return AutonomousResearchManagerEngine()


def _cmd_plan(a) -> int:
    _p({"committed": a.commit,
        "plan": _eng().create_research_plan(a.name, a.objective or "", _now(),
                                           commit=a.commit).to_dict()})
    return 0


def _cmd_task(a) -> int:
    _p({"committed": a.commit,
        "task": _eng().create_task(a.plan, a.name, a.desc or "", a.owner or "", _now(),
                                  commit=a.commit).to_dict()})
    return 0


def _cmd_depend(a) -> int:
    _p({"committed": a.commit,
        "dependency": _eng().resolve_dependency(a.task, a.on, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_progress(a) -> int:
    _p({"committed": a.commit,
        "progress": _eng().track_progress(a.task, a.percent, a.status or "IN_PROGRESS", a.note or "",
                                         _now(), commit=a.commit).to_dict(),
        "note": "TRACK ≠ TRADING"})
    return 0


def _cmd_complete(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().complete_plan(a.plan, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().review_plan(a.plan, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_archive(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().archive_plan(a.plan, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_status_report(a.plan, "PLAN", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_plans(a) -> int:
    eng = _eng()
    ps = eng.list_plans()
    _p({"plans": [{"plan_id": p, "state": eng.current_state(p)} for p in ps]})
    return 0


def _cmd_tasks(a) -> int:
    _p({"tasks": _eng().list_tasks(a.plan)})
    return 0


def _cmd_order(a) -> int:
    _p({"task_order": _eng().task_order(a.plan)})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_manager.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_manager.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_manager")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan")
    pl.add_argument("--name", required=True)
    pl.add_argument("--objective", default="")
    pl.add_argument("--commit", action="store_true")

    tk = sub.add_parser("task")
    tk.add_argument("--plan", required=True)
    tk.add_argument("--name", required=True)
    tk.add_argument("--desc", default="")
    tk.add_argument("--owner", default="")
    tk.add_argument("--commit", action="store_true")

    de = sub.add_parser("depend")
    de.add_argument("--task", required=True)
    de.add_argument("--on", required=True)
    de.add_argument("--commit", action="store_true")

    pg = sub.add_parser("progress")
    pg.add_argument("--task", required=True)
    pg.add_argument("--percent", type=int, default=0)
    pg.add_argument("--status", default="IN_PROGRESS")
    pg.add_argument("--note", default="")
    pg.add_argument("--commit", action="store_true")

    co = sub.add_parser("complete")
    co.add_argument("--plan", required=True)
    co.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--plan", required=True)
    rv.add_argument("--commit", action="store_true")

    ar = sub.add_parser("archive")
    ar.add_argument("--plan", required=True)
    ar.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--plan", required=True)
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("plans")

    ts = sub.add_parser("tasks")
    ts.add_argument("--plan", required=True)

    od = sub.add_parser("order")
    od.add_argument("--plan", required=True)

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"plan": _cmd_plan, "task": _cmd_task, "depend": _cmd_depend, "progress": _cmd_progress,
            "complete": _cmd_complete, "review": _cmd_review, "archive": _cmd_archive,
            "report": _cmd_report, "plans": _cmd_plans, "tasks": _cmd_tasks, "order": _cmd_order,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
