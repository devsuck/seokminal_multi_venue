"""`python -m jarvis.research_task_planner <cmd>` — 자율 연구 태스크 플래너 CLI. **계획 전용.**

  request  --objective --by [--title]           계획 요청(REQUESTED) [--commit]
  task     --plan --name --kind [--parent]       태스크 추가 [--commit]
  depend   --plan --up --down                    의존성 추가(DAG) [--commit]
  finalize --plan                                DAG 검증·확정(PLANNED)+스케줄 [--commit]
  advance  --plan --to RUNNING|COMPLETED|REVIEWED 생애주기 전이 [--commit]
  graph    --plan                                태스크 그래프
  validate --plan                                DAG 검증
  report   --plan [--metrics-json]               계획 리포트 [--commit]
  plans / verify / replay / summary

실제 실행·자동 승인·자동 배포 없음 — 계획만. RUNNING 은 관측 상태 라벨.
PLAN ≠ EXECUTE · SCHEDULE ≠ DEPLOY · GRAPH ≠ APPROVAL.
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
    from jarvis.research_task_planner.engine import ResearchTaskPlannerEngine
    return ResearchTaskPlannerEngine()


def _cmd_request(a) -> int:
    e = _eng().request_plan(a.objective, a.by, a.title or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "plan": e.to_dict()})
    return 0


def _cmd_task(a) -> int:
    t = _eng().add_task(a.plan, a.name, a.kind, a.objective or "", a.parent or "", _now(),
                        commit=a.commit)
    _p({"committed": a.commit, "task": t.to_dict()})
    return 0


def _cmd_depend(a) -> int:
    d = _eng().add_dependency(a.plan, a.up, a.down, _now(), commit=a.commit)
    _p({"committed": a.commit, "dependency": d.to_dict()})
    return 0


def _cmd_finalize(a) -> int:
    _p({"committed": a.commit, "finalized": _eng().finalize_plan(a.plan, _now(), commit=a.commit)})
    return 0


def _cmd_advance(a) -> int:
    e = _eng()
    fn = {"RUNNING": e.mark_running, "COMPLETED": e.mark_completed, "REVIEWED": e.review_plan}[a.to]
    _p({"committed": a.commit, "plan": fn(a.plan, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_graph(a) -> int:
    _p(_eng().build_task_graph(a.plan))
    return 0


def _cmd_validate(a) -> int:
    res = _eng().validate_dag(a.plan)
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report(a.plan, "PLAN", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "note": "GRAPH ≠ APPROVAL"})
    return 0


def _cmd_plans(a) -> int:
    _p({"plans": _eng().list_plans()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_task_planner.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_task_planner.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_task_planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rq = sub.add_parser("request")
    rq.add_argument("--objective", required=True)
    rq.add_argument("--by", required=True)
    rq.add_argument("--title", default="")
    rq.add_argument("--commit", action="store_true")
    tk = sub.add_parser("task")
    tk.add_argument("--plan", required=True)
    tk.add_argument("--name", required=True)
    tk.add_argument("--kind", required=True)
    tk.add_argument("--objective", default="")
    tk.add_argument("--parent", default="")
    tk.add_argument("--commit", action="store_true")
    dp = sub.add_parser("depend")
    dp.add_argument("--plan", required=True)
    dp.add_argument("--up", required=True)
    dp.add_argument("--down", required=True)
    dp.add_argument("--commit", action="store_true")
    fi = sub.add_parser("finalize")
    fi.add_argument("--plan", required=True)
    fi.add_argument("--commit", action="store_true")
    ad = sub.add_parser("advance")
    ad.add_argument("--plan", required=True)
    ad.add_argument("--to", required=True, choices=["RUNNING", "COMPLETED", "REVIEWED"])
    ad.add_argument("--commit", action="store_true")
    gr = sub.add_parser("graph")
    gr.add_argument("--plan", required=True)
    va = sub.add_parser("validate")
    va.add_argument("--plan", required=True)
    rp = sub.add_parser("report")
    rp.add_argument("--plan", required=True)
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("plans")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"request": _cmd_request, "task": _cmd_task, "depend": _cmd_depend,
            "finalize": _cmd_finalize, "advance": _cmd_advance, "graph": _cmd_graph,
            "validate": _cmd_validate, "report": _cmd_report, "plans": _cmd_plans,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
