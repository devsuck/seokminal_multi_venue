"""`python -m jarvis.research_automation <cmd>` — 연구 자동화 오케스트레이션 CLI. **조정·기록 전용.**

  workflow   --name [--version --desc]                워크플로 등록(DRAFT) [--commit]
  pipeline   --workflow --name                        파이프라인 정의(CREATED) [--commit]
  task       --pipeline --name [--type --input]       작업 생성(CREATED) [--commit]
  dependency --parent --child [--relation]            의존 추가(DAG) [--commit]
  run        --pipeline                               연구 실행 시작(→EXECUTING) [--commit]
  report --pipeline / verify / summary / replay

거래·주문·자본 배분·전략 배포·모델 수정·라이브 승인 없음. ORCHESTRATE ≠ EXECUTE · COMPLETED ≠ VALIDATED.
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
    from jarvis.research_automation.engine import ResearchAutomationEngine
    return ResearchAutomationEngine()


def _cmd_workflow(a) -> int:
    _p({"committed": a.commit,
        "workflow": _eng().register_workflow(a.name, a.version, a.desc or "", [], _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_pipeline(a) -> int:
    _p({"committed": a.commit,
        "pipeline": _eng().define_pipeline(a.workflow, a.name, [], _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_task(a) -> int:
    _p({"committed": a.commit,
        "task": _eng().create_task(a.pipeline, a.name, a.type or "research", a.input or "", _now(),
                                  commit=a.commit).to_dict()})
    return 0


def _cmd_dependency(a) -> int:
    _p({"committed": a.commit,
        "dependency": _eng().add_dependency(a.parent, a.child, a.relation or "requires", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_run(a) -> int:
    _p({"committed": a.commit,
        "run": _eng().start_research_run(a.pipeline, "", _now(), commit=a.commit).to_dict(),
        "note": "ORCHESTRATE ≠ EXECUTE"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.pipeline, "PIPELINE", _now(),
                                        commit=a.commit).to_dict(), "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_automation.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_automation.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_automation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    wf = sub.add_parser("workflow")
    wf.add_argument("--name", required=True)
    wf.add_argument("--version", default="1.0")
    wf.add_argument("--desc", default="")
    wf.add_argument("--commit", action="store_true")

    pp = sub.add_parser("pipeline")
    pp.add_argument("--workflow", required=True)
    pp.add_argument("--name", required=True)
    pp.add_argument("--commit", action="store_true")

    tk = sub.add_parser("task")
    tk.add_argument("--pipeline", required=True)
    tk.add_argument("--name", required=True)
    tk.add_argument("--type", default="research")
    tk.add_argument("--input", default="")
    tk.add_argument("--commit", action="store_true")

    de = sub.add_parser("dependency")
    de.add_argument("--parent", required=True)
    de.add_argument("--child", required=True)
    de.add_argument("--relation", default="requires")
    de.add_argument("--commit", action="store_true")

    rn = sub.add_parser("run")
    rn.add_argument("--pipeline", required=True)
    rn.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--pipeline", required=True)
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"workflow": _cmd_workflow, "pipeline": _cmd_pipeline, "task": _cmd_task,
            "dependency": _cmd_dependency, "run": _cmd_run, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
