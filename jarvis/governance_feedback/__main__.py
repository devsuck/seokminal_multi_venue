"""`python -m jarvis.governance_feedback <cmd>` — 거버넌스 피드백 인텔리전스 CLI. **분석·기록 전용.**

  feedback  --source-layer --category --description [--evidence --severity] [--commit]
  issue     --source [--frequency --impact --feedback-ref] [--commit]
  pattern   --issue-type [--sources s1,s2 --occurrences] [--commit]
  theme     --description [--support f1,f2 --priority] [--commit]
  aggregate --period [--metrics-json --prev-score] [--commit]
  report    [--metrics-json] [--commit]
  verify / replay / summary

실제 정책 수정·permission 변경·config 변경·자동 이슈 수정·승인·실행 없음 — 거버넌스 학습 기록만.
FEEDBACK ≠ CHANGE · PATTERN ≠ DECISION · RECOMMENDATION ≠ IMPLEMENTATION · TREND ≠ AUTOMATIC ACTION.
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
    from jarvis.governance_feedback.engine import GovernanceFeedbackEngine
    return GovernanceFeedbackEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_feedback(a) -> int:
    f = _eng().record_feedback(a.source_layer, a.category, a.description, a.evidence or "",
                               a.severity or "MEDIUM", _now(), commit=a.commit)
    _p({"committed": a.commit, "feedback": f.to_dict(), "note": "FEEDBACK ≠ CHANGE"})
    return 0


def _cmd_issue(a) -> int:
    i = _eng().register_issue(a.source, a.frequency or 1, a.impact or "MEDIUM",
                              a.feedback_ref or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "issue": i.to_dict(), "note": "탐지·추적 기록 — 자동 수정 없음"})
    return 0


def _cmd_pattern(a) -> int:
    occ = a.occurrences if a.occurrences is not None else None
    p = _eng().analyze_pattern(a.issue_type, _split(a.sources) or None, occ, _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "pattern": p.to_dict(), "note": "PATTERN ≠ DECISION"})
    return 0


def _cmd_theme(a) -> int:
    t = _eng().create_theme(a.description, _split(a.support), a.priority or "MEDIUM", _now(),
                            commit=a.commit)
    _p({"committed": a.commit, "theme": t.to_dict(), "note": "분석 전용 — RECOMMENDATION ≠ IMPLEMENTATION"})
    return 0


def _cmd_aggregate(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    agg = _eng().aggregate_feedback(a.period, metrics, a.prev_score, _now(), commit=a.commit)
    _p({"committed": a.commit, "aggregation": agg.to_dict(), "note": "TREND ≠ AUTOMATIC ACTION"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.governance_feedback.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.governance_feedback.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.governance_feedback")
    sub = ap.add_subparsers(dest="cmd", required=True)
    fb = sub.add_parser("feedback")
    fb.add_argument("--source-layer", required=True)
    fb.add_argument("--category", required=True)
    fb.add_argument("--description", required=True)
    fb.add_argument("--evidence", default="")
    fb.add_argument("--severity", default="MEDIUM")
    fb.add_argument("--commit", action="store_true")
    iss = sub.add_parser("issue")
    iss.add_argument("--source", required=True)
    iss.add_argument("--frequency", type=int, default=1)
    iss.add_argument("--impact", default="MEDIUM")
    iss.add_argument("--feedback-ref", default="")
    iss.add_argument("--commit", action="store_true")
    pt = sub.add_parser("pattern")
    pt.add_argument("--issue-type", required=True)
    pt.add_argument("--sources", default="")
    pt.add_argument("--occurrences", type=int, default=None)
    pt.add_argument("--commit", action="store_true")
    th = sub.add_parser("theme")
    th.add_argument("--description", required=True)
    th.add_argument("--support", default="")
    th.add_argument("--priority", default="MEDIUM")
    th.add_argument("--commit", action="store_true")
    ag = sub.add_parser("aggregate")
    ag.add_argument("--period", required=True)
    ag.add_argument("--metrics-json", default="")
    ag.add_argument("--prev-score", type=float, default=None)
    ag.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"feedback": _cmd_feedback, "issue": _cmd_issue, "pattern": _cmd_pattern,
            "theme": _cmd_theme, "aggregate": _cmd_aggregate, "report": _cmd_report,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
