"""`python -m jarvis.research_planning <cmd>` — 연구 계획 인텔리전스 CLI. **계획·기록 전용.**

  opportunity --description [--expected-learning --confidence] [--commit]
  plan        --name [--opportunities o1,o2 --complexity --expected-value] [--commit]
  blueprint   --objective --method [--inputs i1,i2 --validation v1,v2] [--commit]
  dependency  --from-node --from-type --edge-type --to-node --to-type [--commit]
  priority    --plan-ref --metrics-json [--commit]
  report      [--scope --metrics-json] [--commit]
  verify / replay / summary

실제 실험 시작·전략 선택·자원 배분·agent 실행·모델 배포 없음 — 계획·분석·기록만.
PLAN ≠ EXECUTION · PRIORITY ≠ APPROVAL · OPPORTUNITY ≠ GUARANTEED VALUE.
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
    from jarvis.research_planning.engine import ResearchPlanningEngine
    return ResearchPlanningEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_opportunity(a) -> int:
    o = _eng().register_opportunity(a.description, [], a.expected_learning or "", a.confidence,
                                    _now(), commit=a.commit)
    _p({"committed": a.commit, "opportunity": o.to_dict(), "note": "OPPORTUNITY ≠ VALUE"})
    return 0


def _cmd_plan(a) -> int:
    p = _eng().create_plan(a.name, _split(a.opportunities), [], {}, a.complexity,
                           a.expected_value or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "plan": p.to_dict(), "note": "priority 는 정보용 — PRIORITY ≠ APPROVAL"})
    return 0


def _cmd_blueprint(a) -> int:
    b = _eng().create_blueprint(a.objective, _split(a.inputs), a.method, _split(a.validation),
                                [], _now(), commit=a.commit)
    _p({"committed": a.commit, "blueprint": b.to_dict(), "note": "실행 없음 — PLAN ≠ EXECUTION"})
    return 0


def _cmd_dependency(a) -> int:
    eng = _eng()
    d = eng.add_dependency(a.from_node, a.from_type, a.edge_type, a.to_node, a.to_type, _now(),
                           commit=a.commit)
    _p({"committed": a.commit, "dependency": d.to_dict(), "cycle": eng.dependency_cycle()})
    return 0


def _cmd_priority(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    pr = _eng().prioritize(a.plan_ref, metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "priority": pr.to_dict(), "note": "정보용 — 승인 아님"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report(a.scope or "GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_planning.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_planning.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_planning")
    sub = ap.add_subparsers(dest="cmd", required=True)
    op = sub.add_parser("opportunity")
    op.add_argument("--description", required=True)
    op.add_argument("--expected-learning", default="")
    op.add_argument("--confidence", type=float, default=0.0)
    op.add_argument("--commit", action="store_true")
    pl = sub.add_parser("plan")
    pl.add_argument("--name", required=True)
    pl.add_argument("--opportunities", default="")
    pl.add_argument("--complexity", default="MEDIUM", choices=("LOW", "MEDIUM", "HIGH"))
    pl.add_argument("--expected-value", default="")
    pl.add_argument("--commit", action="store_true")
    bp = sub.add_parser("blueprint")
    bp.add_argument("--objective", required=True)
    bp.add_argument("--method", required=True)
    bp.add_argument("--inputs", default="")
    bp.add_argument("--validation", default="")
    bp.add_argument("--commit", action="store_true")
    de = sub.add_parser("dependency")
    for f in ("from-node", "from-type", "edge-type", "to-node", "to-type"):
        de.add_argument(f"--{f}", required=True)
    de.add_argument("--commit", action="store_true")
    pr = sub.add_parser("priority")
    pr.add_argument("--plan-ref", required=True)
    pr.add_argument("--metrics-json", default="")
    pr.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="GLOBAL")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"opportunity": _cmd_opportunity, "plan": _cmd_plan, "blueprint": _cmd_blueprint,
            "dependency": _cmd_dependency, "priority": _cmd_priority, "report": _cmd_report,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
