"""`python -m jarvis.research_orchestration <cmd>` — 연구 오케스트레이션 CLI. **가시성·조정·기록 전용.**

  workflow   --name [--version --objective] [--commit]
  pipeline   --workflow-id [--stages s1,s2 --version] [--commit]
  task       --workflow-id --name [--type --deps t1,t2] [--commit]
  dependency --from-task --to-task [--commit]
  event      --scope --event-type --reference [--commit]
  bottleneck --source-task --category [--severity] [--commit]
  report     [--metrics-json] [--commit]
  verify / replay / summary

실제 실행·거래·배포·portfolio 수정·order 생성·capital 배분·자동 트리거 없음 — 과정 가시성·기록만.
WORKFLOW STATE ≠ EXECUTION STATE · TASK READY ≠ RUNNING PROCESS · WORKFLOW COMPLETED ≠ DEPLOYMENT · ORCHESTRATION ≠ AUTOMATION.
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
    from jarvis.research_orchestration.engine import ResearchOrchestrationEngine
    return ResearchOrchestrationEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_workflow(a) -> int:
    w = _eng().create_workflow(a.name, a.version or "1.0", a.objective or "", {}, _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "workflow": w.to_dict(), "note": "레지스트리 — 실행 아님"})
    return 0


def _cmd_pipeline(a) -> int:
    p = _eng().create_pipeline(a.workflow_id, _split(a.stages), a.version or "1.0", {}, _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "pipeline": p.to_dict(), "note": "정의 — 버전 불변"})
    return 0


def _cmd_task(a) -> int:
    t = _eng().register_task(a.workflow_id, a.name, a.type or "ANALYSIS", _split(a.deps), _now(),
                             commit=a.commit)
    _p({"committed": a.commit, "task": t.to_dict(), "note": "TASK READY ≠ RUNNING PROCESS"})
    return 0


def _cmd_dependency(a) -> int:
    eng = _eng()
    d = eng.add_dependency(a.from_task, a.to_task, "REQUIRES", _now(), commit=a.commit)
    _p({"committed": a.commit, "dependency": d.to_dict(), "cycle": eng.dependency_cycle()})
    return 0


def _cmd_event(a) -> int:
    e = _eng().record_event(a.scope, a.event_type, a.reference, _now(), commit=a.commit)
    _p({"committed": a.commit, "event": e.to_dict()})
    return 0


def _cmd_bottleneck(a) -> int:
    b = _eng().detect_bottleneck(a.source_task, a.category, a.severity or "MEDIUM", [], _now(),
                                 commit=a.commit)
    _p({"committed": a.commit, "bottleneck": b.to_dict(), "note": "플래그·기록만 — 자동 조치 없음"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_orchestration.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_orchestration.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_orchestration")
    sub = ap.add_subparsers(dest="cmd", required=True)
    wf = sub.add_parser("workflow")
    wf.add_argument("--name", required=True)
    wf.add_argument("--version", default="1.0")
    wf.add_argument("--objective", default="")
    wf.add_argument("--commit", action="store_true")
    pl = sub.add_parser("pipeline")
    pl.add_argument("--workflow-id", required=True)
    pl.add_argument("--stages", default="")
    pl.add_argument("--version", default="1.0")
    pl.add_argument("--commit", action="store_true")
    tk = sub.add_parser("task")
    tk.add_argument("--workflow-id", required=True)
    tk.add_argument("--name", required=True)
    tk.add_argument("--type", default="ANALYSIS")
    tk.add_argument("--deps", default="")
    tk.add_argument("--commit", action="store_true")
    dp = sub.add_parser("dependency")
    dp.add_argument("--from-task", required=True)
    dp.add_argument("--to-task", required=True)
    dp.add_argument("--commit", action="store_true")
    ev = sub.add_parser("event")
    ev.add_argument("--scope", required=True)
    ev.add_argument("--event-type", required=True)
    ev.add_argument("--reference", required=True)
    ev.add_argument("--commit", action="store_true")
    bn = sub.add_parser("bottleneck")
    bn.add_argument("--source-task", required=True)
    bn.add_argument("--category", required=True)
    bn.add_argument("--severity", default="MEDIUM")
    bn.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"workflow": _cmd_workflow, "pipeline": _cmd_pipeline, "task": _cmd_task,
            "dependency": _cmd_dependency, "event": _cmd_event, "bottleneck": _cmd_bottleneck,
            "report": _cmd_report, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
