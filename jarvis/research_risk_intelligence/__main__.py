"""`python -m jarvis.research_risk_intelligence <cmd>` — 연구 리스크 인텔리전스 CLI. **분석·기록 전용.**

  risk     --source-layer --source-reference --category [--commit]
  factor   --risk-ref --name --category --value [--weight] [--commit]
  assess   --risk-ref [--scores-json --evidence --epoch] [--commit]
  review   --risk-ref [--commit]
  report   [--metrics-json] [--commit]
  verify / replay / summary

실제 리스크 한도 변경·자본 결정·전략 거부·배포 결정 없음 — 연구 과정 리스크 분석·기록만(투자 실행 리스크 아님).
RISK ANALYSIS ≠ RISK LIMIT CHANGE · ASSESSMENT ≠ CAPITAL DECISION · FINDING ≠ STRATEGY REJECTION · SCORE ≠ DEPLOYMENT DECISION.
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
    from jarvis.research_risk_intelligence.engine import ResearchRiskIntelligenceEngine
    return ResearchRiskIntelligenceEngine()


def _cmd_risk(a) -> int:
    r = _eng().register_risk(a.source_layer, a.source_reference, a.category, _now(),
                             commit=a.commit)
    _p({"committed": a.commit, "risk": r.to_dict(), "note": "추적 시작 — 결정 없음"})
    return 0


def _cmd_factor(a) -> int:
    f = _eng().record_factor(a.risk_ref, a.name, a.category, a.value, a.weight or 1.0, "", _now(),
                             commit=a.commit)
    _p({"committed": a.commit, "factor": f.to_dict()})
    return 0


def _cmd_assess(a) -> int:
    scores = json.loads(a.scores_json) if a.scores_json else None
    r = _eng().assess_risk(a.risk_ref, scores, a.evidence or "", a.epoch or "", _now(),
                           commit=a.commit)
    _p({"committed": a.commit, "assessment": r.to_dict(), "note": "SCORE ≠ DEPLOYMENT DECISION"})
    return 0


def _cmd_review(a) -> int:
    res = _eng().review_risk(a.risk_ref, _now(), commit=a.commit)
    _p({"committed": a.commit, "review": res})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_risk_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_risk_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_risk_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ri = sub.add_parser("risk")
    ri.add_argument("--source-layer", required=True)
    ri.add_argument("--source-reference", required=True)
    ri.add_argument("--category", required=True)
    ri.add_argument("--commit", action="store_true")
    fa = sub.add_parser("factor")
    fa.add_argument("--risk-ref", required=True)
    fa.add_argument("--name", required=True)
    fa.add_argument("--category", required=True)
    fa.add_argument("--value", type=float, required=True)
    fa.add_argument("--weight", type=float, default=1.0)
    fa.add_argument("--commit", action="store_true")
    ase = sub.add_parser("assess")
    ase.add_argument("--risk-ref", required=True)
    ase.add_argument("--scores-json", default="")
    ase.add_argument("--evidence", default="")
    ase.add_argument("--epoch", default="")
    ase.add_argument("--commit", action="store_true")
    rv = sub.add_parser("review")
    rv.add_argument("--risk-ref", required=True)
    rv.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"risk": _cmd_risk, "factor": _cmd_factor, "assess": _cmd_assess,
            "review": _cmd_review, "report": _cmd_report, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
