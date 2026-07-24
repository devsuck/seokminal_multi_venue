"""`python -m jarvis.research_agent_coordinator <cmd>` — 연구 에이전트 조정 CLI. **조정·기록 전용.**

  assign     --coordinator --agent [--capability]        에이전트 배정(로스터) [--commit]
  task       --coordinator --task --agent [--note]       작업 배정(CREATED→ASSIGNED) [--commit]
  progress   --assignment [--percent --note --result]    진행 기록(→IN_PROGRESS) [--commit]
  handoff    --assignment --to --evidence [--note]       핸드오프(→HANDOFF) [--commit]
  review     --assignment                                리뷰 제출(→REVIEW) [--commit]
  complete   --assignment --result                       완료(→COMPLETED) [--commit]
  conflict   --task --winning [--agents]                 상충 해소 기록 [--commit]
  report     --coordinator / assignments [--coordinator] / verify / replay / summary

실제 외부 실행 없음 — 조정·기록만. COORDINATE ≠ EXECUTION · ASSIGN ≠ AUTHORIZATION · HANDOFF ≠ DEPLOYMENT.
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
    from jarvis.research_agent_coordinator.engine import ResearchAgentCoordinatorEngine
    return ResearchAgentCoordinatorEngine()


def _cmd_assign(a) -> int:
    _p({"committed": a.commit,
        "agent": _eng().assign_agent(a.coordinator, a.agent, a.capability or "", _now(),
                                     commit=a.commit).to_dict()})
    return 0


def _cmd_task(a) -> int:
    _p({"committed": a.commit,
        "assignment": _eng().create_task_assignment(a.coordinator, a.task, a.agent, a.note or "",
                                                   _now(), commit=a.commit).to_dict(),
        "note": "ASSIGN ≠ AUTHORIZATION"})
    return 0


def _cmd_progress(a) -> int:
    _p({"committed": a.commit,
        "progress": _eng().track_progress(a.assignment, a.percent, a.note or "", a.result or "",
                                         _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_handoff(a) -> int:
    _p({"committed": a.commit,
        "handoff": _eng().record_handoff(a.assignment, a.to, a.evidence, a.note or "", _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().submit_for_review(a.assignment, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_complete(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().complete_assignment(a.assignment, a.result, _now(),
                                           commit=a.commit).to_dict()})
    return 0


def _cmd_conflict(a) -> int:
    agents = a.agents.split(",") if a.agents else []
    _p({"committed": a.commit,
        "collaboration": _eng().resolve_assignment_conflict(a.task, agents, a.winning, "", _now(),
                                                           commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_coordination_report(a.coordinator, "ALL", _now(),
                                                     commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_assignments(a) -> int:
    eng = _eng()
    xs = eng.list_assignments(a.coordinator or "")
    _p({"assignments": [{"assignment_id": x, "state": eng.current_state(x),
                         "owner": eng.current_owner(x)} for x in xs]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_agent_coordinator.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_agent_coordinator.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_agent_coordinator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ag = sub.add_parser("assign")
    ag.add_argument("--coordinator", required=True)
    ag.add_argument("--agent", required=True)
    ag.add_argument("--capability", default="")
    ag.add_argument("--commit", action="store_true")

    tk = sub.add_parser("task")
    tk.add_argument("--coordinator", required=True)
    tk.add_argument("--task", required=True)
    tk.add_argument("--agent", required=True)
    tk.add_argument("--note", default="")
    tk.add_argument("--commit", action="store_true")

    pg = sub.add_parser("progress")
    pg.add_argument("--assignment", required=True)
    pg.add_argument("--percent", type=int, default=0)
    pg.add_argument("--note", default="")
    pg.add_argument("--result", default="")
    pg.add_argument("--commit", action="store_true")

    ho = sub.add_parser("handoff")
    ho.add_argument("--assignment", required=True)
    ho.add_argument("--to", required=True)
    ho.add_argument("--evidence", required=True)
    ho.add_argument("--note", default="")
    ho.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--assignment", required=True)
    rv.add_argument("--commit", action="store_true")

    co = sub.add_parser("complete")
    co.add_argument("--assignment", required=True)
    co.add_argument("--result", required=True)
    co.add_argument("--commit", action="store_true")

    cf = sub.add_parser("conflict")
    cf.add_argument("--task", required=True)
    cf.add_argument("--winning", required=True)
    cf.add_argument("--agents", default="")
    cf.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--coordinator", required=True)
    rp.add_argument("--commit", action="store_true")

    asg = sub.add_parser("assignments")
    asg.add_argument("--coordinator", default="")

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"assign": _cmd_assign, "task": _cmd_task, "progress": _cmd_progress,
            "handoff": _cmd_handoff, "review": _cmd_review, "complete": _cmd_complete,
            "conflict": _cmd_conflict, "report": _cmd_report, "assignments": _cmd_assignments,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
