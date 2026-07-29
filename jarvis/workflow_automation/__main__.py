"""`python -m jarvis.workflow_automation <cmd>` — 워크플로 조율 CLI. **자율 실행 없음.**

  workflow  --name [--description]                          워크플로 등록(CREATED) [--commit]
  advance   --workflow --to                                 워크플로 상태 전이 [--commit]
  task      --workflow --name [--kind]                      태스크 추가(PENDING) [--commit]
  task-adv  --task --to                                     태스크 상태 전이 [--commit]
  depend    --workflow --from-task --to-task                의존성 [--commit]
  review    --workflow --stage [--note]                     사람 검토 요청 [--commit]
  metadata  --workflow --key --value                        메타 [--commit]
  order     --workflow                                      권고 실행 순서(위상정렬)
  report [--scope] / verify / summary / replay

자율 실행·거래·배포·자본 배분 없음. WORKFLOW AUTOMATION ≠ AUTONOMOUS EXECUTION · 사람 승인 필수.
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
    from jarvis.workflow_automation.engine import WorkflowAutomationEngine
    return WorkflowAutomationEngine()


def _cmd_workflow(a) -> int:
    _p({"committed": a.commit,
        "workflow": _eng().create_workflow(a.name, a.description or "", _now(),
                                           commit=a.commit).to_dict()})
    return 0


def _cmd_advance(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().advance_state(a.workflow, a.to, "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_task(a) -> int:
    _p({"committed": a.commit,
        "task": _eng().add_task(a.workflow, a.name, a.kind or "ANALYSIS", _now(),
                                commit=a.commit).to_dict()})
    return 0


def _cmd_task_adv(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().advance_task(a.task, a.to, "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_depend(a) -> int:
    _p({"committed": a.commit,
        "dependency": _eng().track_dependency(a.workflow, a.from_task, a.to_task, _now(),
                                             commit=a.commit).to_dict()})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "approval": _eng().request_review(a.workflow, a.stage, a.note or "", _now(),
                                         commit=a.commit).to_dict(),
        "note": "is_granted=False · 사람 승인 필수"})
    return 0


def _cmd_metadata(a) -> int:
    _p({"committed": a.commit,
        "metadata": _eng().record_metadata(a.workflow, a.key, a.value, _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_order(a) -> int:
    _p({"workflow": a.workflow, "recommended_order": _eng().task_execution_order(a.workflow),
        "note": "권고 순서일 뿐 — 자동 실행 아님"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_workflow_report(a.scope or "SYSTEM", _now(),
                                                  commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.workflow_automation.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.workflow_automation.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.workflow_automation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    wf = sub.add_parser("workflow")
    wf.add_argument("--name", required=True)
    wf.add_argument("--description", default="")
    wf.add_argument("--commit", action="store_true")

    av = sub.add_parser("advance")
    av.add_argument("--workflow", required=True)
    av.add_argument("--to", required=True)
    av.add_argument("--commit", action="store_true")

    tk = sub.add_parser("task")
    tk.add_argument("--workflow", required=True)
    tk.add_argument("--name", required=True)
    tk.add_argument("--kind", default="ANALYSIS")
    tk.add_argument("--commit", action="store_true")

    ta = sub.add_parser("task-adv")
    ta.add_argument("--task", required=True)
    ta.add_argument("--to", required=True)
    ta.add_argument("--commit", action="store_true")

    dp = sub.add_parser("depend")
    dp.add_argument("--workflow", required=True)
    dp.add_argument("--from-task", dest="from_task", required=True)
    dp.add_argument("--to-task", dest="to_task", required=True)
    dp.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--workflow", required=True)
    rv.add_argument("--stage", required=True)
    rv.add_argument("--note", default="")
    rv.add_argument("--commit", action="store_true")

    md = sub.add_parser("metadata")
    md.add_argument("--workflow", required=True)
    md.add_argument("--key", required=True)
    md.add_argument("--value", required=True)
    md.add_argument("--commit", action="store_true")

    od = sub.add_parser("order")
    od.add_argument("--workflow", required=True)

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"workflow": _cmd_workflow, "advance": _cmd_advance, "task": _cmd_task,
            "task-adv": _cmd_task_adv, "depend": _cmd_depend, "review": _cmd_review,
            "metadata": _cmd_metadata, "order": _cmd_order, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
