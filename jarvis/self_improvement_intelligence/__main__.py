"""`python -m jarvis.self_improvement_intelligence <cmd>` — 연구 자기개선 분석 CLI. **분석·제안 전용.**

  workflow       --name --steps s1,s2 [--source-ref] [--commit]
  opportunity    --category --description [--severity --confidence] [--commit]
  bottleneck     --type [--frequency --impact] [--commit]
  recommendation --target-process --suggestion [--expected-benefit --confidence] [--accept] [--commit]
  template       --name --version [--reason] [--commit]
  report         [--scope --metrics-json] [--commit]
  verify / replay / summary

실제 실행·거래·배포·전략/모델 수정·자동 적용 없음 — 분석·제안·기록만.
IMPROVEMENT SUGGESTION ≠ ACTION · RECOMMENDATION ≠ APPROVAL · INSIGHT ≠ EXECUTION.
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
    from jarvis.self_improvement_intelligence.engine import ResearchSelfImprovementEngine
    return ResearchSelfImprovementEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_workflow(a) -> int:
    w = _eng().register_workflow(a.name, _split(a.steps), a.source_ref or "", [], {}, _now(),
                                 commit=a.commit)
    _p({"committed": a.commit, "workflow": w.to_dict(), "note": "연구 워크플로 — 수정 아님"})
    return 0


def _cmd_opportunity(a) -> int:
    o = _eng().record_opportunity(a.category, a.description, a.severity, [], a.confidence, "",
                                  _now(), commit=a.commit)
    _p({"committed": a.commit, "opportunity": o.to_dict(), "note": "SUGGESTION ≠ ACTION"})
    return 0


def _cmd_bottleneck(a) -> int:
    b = _eng().analyze_bottleneck(a.type, a.frequency, a.impact, [], _now(), commit=a.commit)
    _p({"committed": a.commit, "bottleneck": b.to_dict()})
    return 0


def _cmd_recommendation(a) -> int:
    eng = _eng()
    r = eng.create_recommendation(a.target_process, a.suggestion, a.expected_benefit or "", [],
                                  a.confidence, "", _now(), commit=a.commit)
    if a.accept:
        eng.accept_recommendation(r.recommendation_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "recommendation": r.to_dict(),
        "note": "ACCEPTED = 사람 인지일 뿐 · 자동 적용 없음"})
    return 0


def _cmd_template(a) -> int:
    t = _eng().track_template_change(a.name, a.version, [], a.reason or "", [], "", _now(),
                                     commit=a.commit)
    _p({"committed": a.commit, "template": t.to_dict(), "note": "자동 마이그레이션 없음"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_improvement_report(a.scope or "GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.self_improvement_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.self_improvement_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.self_improvement_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    wf = sub.add_parser("workflow")
    wf.add_argument("--name", required=True)
    wf.add_argument("--steps", default="")
    wf.add_argument("--source-ref", default="")
    wf.add_argument("--commit", action="store_true")
    op = sub.add_parser("opportunity")
    op.add_argument("--category", required=True)
    op.add_argument("--description", required=True)
    op.add_argument("--severity", default="MEDIUM")
    op.add_argument("--confidence", type=float, default=0.0)
    op.add_argument("--commit", action="store_true")
    bo = sub.add_parser("bottleneck")
    bo.add_argument("--type", required=True)
    bo.add_argument("--frequency", type=int, default=1)
    bo.add_argument("--impact", default="MEDIUM")
    bo.add_argument("--commit", action="store_true")
    re = sub.add_parser("recommendation")
    re.add_argument("--target-process", required=True)
    re.add_argument("--suggestion", required=True)
    re.add_argument("--expected-benefit", default="")
    re.add_argument("--confidence", type=float, default=0.0)
    re.add_argument("--accept", action="store_true")
    re.add_argument("--commit", action="store_true")
    te = sub.add_parser("template")
    te.add_argument("--name", required=True)
    te.add_argument("--version", required=True)
    te.add_argument("--reason", default="")
    te.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="GLOBAL")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"workflow": _cmd_workflow, "opportunity": _cmd_opportunity,
            "bottleneck": _cmd_bottleneck, "recommendation": _cmd_recommendation,
            "template": _cmd_template, "report": _cmd_report, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
