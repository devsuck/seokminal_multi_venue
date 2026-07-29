"""`python -m jarvis.research_lifecycle <cmd>` — 연구 생명주기 인텔리전스 CLI. **추적·기록 전용.**

  project    --name [--source-layer --source-reference] [--commit]
  advance    --project-ref --to-stage [--note] [--commit]
  event      --project-ref --event-type --reference [--detail] [--commit]
  bottleneck --project-ref --stage --category [--severity --detail] [--commit]
  missing    --project-ref
  report     [--metrics-json] [--commit]
  verify / replay / summary

실제 실행·배포·승인·거래 없음 — 연구 생명주기 추적·기록만.
LIFECYCLE TRACKING ≠ EXECUTION · TRANSITION ≠ APPROVAL · STAGE ≠ DEPLOYMENT · RECORD ≠ DECISION.
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
    from jarvis.research_lifecycle.engine import ResearchLifecycleEngine
    return ResearchLifecycleEngine()


def _cmd_project(a) -> int:
    p = _eng().register_project(a.name, a.source_layer or "", a.source_reference or "", _now(),
                                commit=a.commit)
    _p({"committed": a.commit, "project": p.to_dict(), "note": "추적 시작 — 결정/승인 없음"})
    return 0


def _cmd_advance(a) -> int:
    res = _eng().advance_stage(a.project_ref, a.to_stage, a.note or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "advance": res, "note": "TRANSITION ≠ APPROVAL"})
    return 0


def _cmd_event(a) -> int:
    e = _eng().record_event(a.project_ref, a.event_type, a.reference, a.detail or "", _now(),
                            commit=a.commit)
    _p({"committed": a.commit, "event": e.to_dict()})
    return 0


def _cmd_bottleneck(a) -> int:
    b = _eng().record_bottleneck(a.project_ref, a.stage, a.category, a.severity or "MEDIUM",
                                 a.detail or "", [], _now(), commit=a.commit)
    _p({"committed": a.commit, "bottleneck": b.to_dict(), "note": "탐지·기록만"})
    return 0


def _cmd_missing(a) -> int:
    _p({"project_ref": a.project_ref, "missing_stages": _eng().detect_missing_stages(a.project_ref),
        "completion": _eng().completion(a.project_ref)})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_lifecycle.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_lifecycle.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_lifecycle")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("project")
    pr.add_argument("--name", required=True)
    pr.add_argument("--source-layer", default="")
    pr.add_argument("--source-reference", default="")
    pr.add_argument("--commit", action="store_true")
    av = sub.add_parser("advance")
    av.add_argument("--project-ref", required=True)
    av.add_argument("--to-stage", required=True)
    av.add_argument("--note", default="")
    av.add_argument("--commit", action="store_true")
    ev = sub.add_parser("event")
    ev.add_argument("--project-ref", required=True)
    ev.add_argument("--event-type", required=True)
    ev.add_argument("--reference", required=True)
    ev.add_argument("--detail", default="")
    ev.add_argument("--commit", action="store_true")
    bn = sub.add_parser("bottleneck")
    bn.add_argument("--project-ref", required=True)
    bn.add_argument("--stage", required=True)
    bn.add_argument("--category", required=True)
    bn.add_argument("--severity", default="MEDIUM")
    bn.add_argument("--detail", default="")
    bn.add_argument("--commit", action="store_true")
    mi = sub.add_parser("missing")
    mi.add_argument("--project-ref", required=True)
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"project": _cmd_project, "advance": _cmd_advance, "event": _cmd_event,
            "bottleneck": _cmd_bottleneck, "missing": _cmd_missing, "report": _cmd_report,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
