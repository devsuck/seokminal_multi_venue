"""`python -m jarvis.research_operations <cmd>` — 연구 운영 오케스트레이션 CLI. **조정·계획·추적 전용.**

  workflow  --name [--desc]                        워크플로 생성(DRAFT) [--commit]
  task      --workflow --name [--desc --owner --priority]  작업 추가(CREATED) [--commit]
  depend    --task --on                            의존 추가(DAG) [--commit]
  ready --workflow / run --workflow                READY / 런 시작(→RUNNING) [--commit]
  complete-task --task / fail-task --task          작업 완료·실패 [--commit]
  complete --workflow / fail --workflow / archive --workflow
  plan --workflow / order --workflow / report --workflow
  workflows / tasks --workflow / verify / replay / summary

거래·전략 배포·권한 변경·자동 실행·자동 승인 없음. ORCHESTRATE ≠ EXECUTE · PLAN ≠ DEPLOYMENT.
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
    from jarvis.research_operations.engine import ResearchOperationsEngine
    return ResearchOperationsEngine()


def _cmd_workflow(a) -> int:
    _p({"committed": a.commit,
        "workflow": _eng().create_workflow(a.name, a.desc or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_task(a) -> int:
    _p({"committed": a.commit,
        "task": _eng().add_task(a.workflow, a.name, a.desc or "", a.owner or "", a.priority, {},
                               _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_depend(a) -> int:
    _p({"committed": a.commit,
        "dependency": _eng().add_dependency(a.task, a.on, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_ready(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().ready_workflow(a.workflow, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_run(a) -> int:
    _p({"committed": a.commit,
        "run": _eng().start_run(a.workflow, "", "", _now(), commit=a.commit).to_dict(),
        "note": "ORCHESTRATE ≠ EXECUTE"})
    return 0


def _cmd_complete_task(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().complete_task(a.task, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_fail_task(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().fail_task(a.task, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_complete(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().complete_workflow(a.workflow, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_fail(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().fail_workflow(a.workflow, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_archive(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().archive_workflow(a.workflow, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_plan(a) -> int:
    _p({"committed": a.commit,
        "plan": _eng().build_execution_plan(a.workflow, _now(), commit=a.commit).to_dict(),
        "note": "is_proposal=True — 자동 실행 없음"})
    return 0


def _cmd_order(a) -> int:
    _p({"task_order": _eng().task_order(a.workflow)})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.workflow, "WORKFLOW", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_workflows(a) -> int:
    eng = _eng()
    _p({"workflows": [{"workflow_id": w, "state": eng.workflow_state(w)}
                      for w in eng.list_workflows()]})
    return 0


def _cmd_tasks(a) -> int:
    eng = _eng()
    _p({"tasks": [{"task_id": t, "status": eng.task_status(t)}
                  for t in eng.list_tasks(a.workflow)]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_operations.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_operations.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_operations")
    sub = ap.add_subparsers(dest="cmd", required=True)

    wf = sub.add_parser("workflow")
    wf.add_argument("--name", required=True)
    wf.add_argument("--desc", default="")
    wf.add_argument("--commit", action="store_true")

    tk = sub.add_parser("task")
    tk.add_argument("--workflow", required=True)
    tk.add_argument("--name", required=True)
    tk.add_argument("--desc", default="")
    tk.add_argument("--owner", default="")
    tk.add_argument("--priority", type=int, default=0)
    tk.add_argument("--commit", action="store_true")

    de = sub.add_parser("depend")
    de.add_argument("--task", required=True)
    de.add_argument("--on", required=True)
    de.add_argument("--commit", action="store_true")

    for name in ("ready", "run", "complete", "fail", "archive", "plan", "order", "report"):
        sp = sub.add_parser(name)
        sp.add_argument("--workflow", required=True)
        if name not in ("order",):
            sp.add_argument("--commit", action="store_true")

    for name in ("complete-task", "fail-task"):
        sp = sub.add_parser(name)
        sp.add_argument("--task", required=True)
        sp.add_argument("--commit", action="store_true")

    sub.add_parser("workflows")
    ts = sub.add_parser("tasks")
    ts.add_argument("--workflow", required=True)
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"workflow": _cmd_workflow, "task": _cmd_task, "depend": _cmd_depend, "ready": _cmd_ready,
            "run": _cmd_run, "complete-task": _cmd_complete_task, "fail-task": _cmd_fail_task,
            "complete": _cmd_complete, "fail": _cmd_fail, "archive": _cmd_archive, "plan": _cmd_plan,
            "order": _cmd_order, "report": _cmd_report, "workflows": _cmd_workflows,
            "tasks": _cmd_tasks, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
