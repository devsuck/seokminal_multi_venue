"""`python -m jarvis.meta_intelligence <cmd>` — 연구 메타 분석 CLI. **분석·기록 전용.**

  pattern  --category --description [--frequency --confidence] [--commit]
  method   --name --version [--category] [--commit]
  outcome  --source-layer --research-object --result-type [--validation-ref --method-ref] [--commit]
  failure  --category [--occurrences --confidence] [--commit]
  quality  --research-object --components-json [--commit]
  insight  --topic --statement [--metrics-json] [--commit]
  report   [--scope] [--commit]
  verify / replay / summary

실제 실행·거래·배포·자본배분·strategy 선택·model 승인 없음 — 연구 이력 분석·기록만.
META SCORE ≠ TRADING SCORE · INSIGHT ≠ DECISION.
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
    from jarvis.meta_intelligence.engine import ResearchMetaEngine
    return ResearchMetaEngine()


def _cmd_pattern(a) -> int:
    p = _eng().register_pattern(a.category, a.description, a.frequency, [], a.confidence, _now(),
                                commit=a.commit)
    _p({"committed": a.commit, "pattern": p.to_dict(), "note": "연구 패턴 — 실행 아님"})
    return 0


def _cmd_method(a) -> int:
    m = _eng().register_method(a.name, a.version, a.category or "", 0, 0.0, {}, _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "method": m.to_dict()})
    return 0


def _cmd_outcome(a) -> int:
    o = _eng().record_outcome(a.source_layer, a.research_object, a.result_type, {},
                              a.validation_ref or "", a.method_ref or "", _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "outcome": o.to_dict(), "note": "이력 — 자동 판단 아님"})
    return 0


def _cmd_failure(a) -> int:
    f = _eng().record_failure(a.category, a.occurrences, [], a.confidence, _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "failure": f.to_dict()})
    return 0


def _cmd_quality(a) -> int:
    comps = json.loads(a.components_json)
    q = _eng().calculate_quality(a.research_object, comps, _now(), commit=a.commit)
    _p({"committed": a.commit, "quality": q.to_dict(),
        "note": "quality_score ≠ strategy ranking ≠ performance"})
    return 0


def _cmd_insight(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    i = _eng().generate_insight(a.topic, a.statement, metrics, [], _now(), commit=a.commit)
    _p({"committed": a.commit, "insight": i.to_dict(), "note": "INSIGHT ≠ DECISION"})
    return 0


def _cmd_report(a) -> int:
    r = _eng().generate_meta_report(a.scope or "GLOBAL", _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "analysis": _eng().analyze()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.meta_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.meta_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.meta_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("pattern")
    pa.add_argument("--category", required=True)
    pa.add_argument("--description", required=True)
    pa.add_argument("--frequency", type=int, default=1)
    pa.add_argument("--confidence", type=float, default=0.0)
    pa.add_argument("--commit", action="store_true")
    me = sub.add_parser("method")
    me.add_argument("--name", required=True)
    me.add_argument("--version", required=True)
    me.add_argument("--category", default="")
    me.add_argument("--commit", action="store_true")
    ou = sub.add_parser("outcome")
    ou.add_argument("--source-layer", required=True)
    ou.add_argument("--research-object", required=True)
    ou.add_argument("--result-type", required=True,
                    choices=("SUCCESS", "FAILED", "WARNING", "INCONCLUSIVE"))
    ou.add_argument("--validation-ref", default="")
    ou.add_argument("--method-ref", default="")
    ou.add_argument("--commit", action="store_true")
    fa = sub.add_parser("failure")
    fa.add_argument("--category", required=True)
    fa.add_argument("--occurrences", type=int, default=1)
    fa.add_argument("--confidence", type=float, default=0.0)
    fa.add_argument("--commit", action="store_true")
    qu = sub.add_parser("quality")
    qu.add_argument("--research-object", required=True)
    qu.add_argument("--components-json", required=True)
    qu.add_argument("--commit", action="store_true")
    ins = sub.add_parser("insight")
    ins.add_argument("--topic", required=True)
    ins.add_argument("--statement", required=True)
    ins.add_argument("--metrics-json", default="")
    ins.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="GLOBAL")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"pattern": _cmd_pattern, "method": _cmd_method, "outcome": _cmd_outcome,
            "failure": _cmd_failure, "quality": _cmd_quality, "insight": _cmd_insight,
            "report": _cmd_report, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
