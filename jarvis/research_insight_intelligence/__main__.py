"""`python -m jarvis.research_insight_intelligence <cmd>` — 연구 통찰·해석 CLI. **해석 지능 전용.**

  context      --domain [--description --refs]              맥락 생성 [--commit]
  insight      --category --statement [--confidence --context]  통찰 추출(CREATED) [--commit]
  interpret    --insight --explanation [--supporting --conflicting]  증거 해석 [--commit]
  gap          --type --description [--missing]             연구 공백 탐지 [--commit]
  relationship --source --target --relation                 통찰 관계 매핑 [--commit]
  report [--scope] / verify / summary / replay

전략 선택·가설 승인·모델 배포·실험 실행·거래·자본 배분 없음. INSIGHT ≠ DECISION · INSIGHT ≠ RECOMMENDATION.
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
    from jarvis.research_insight_intelligence.engine import ResearchInsightEngine
    return ResearchInsightEngine()


def _split(s):
    return [x for x in (s or "").split("|") if x]


def _cmd_context(a) -> int:
    _p({"committed": a.commit,
        "context": _eng().create_context(a.domain, _split(a.refs), a.description or "", _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_insight(a) -> int:
    _p({"committed": a.commit,
        "insight": _eng().extract_insight(_split(a.refs), a.category, a.statement, a.confidence,
                                        a.context or "", _now(), commit=a.commit).to_dict(),
        "note": "INSIGHT ≠ DECISION"})
    return 0


def _cmd_interpret(a) -> int:
    _p({"committed": a.commit,
        "interpretation": _eng().interpret_evidence(a.insight, a.explanation, _split(a.supporting),
                                                   _split(a.conflicting), a.source or "", _now(),
                                                   commit=a.commit).to_dict()})
    return 0


def _cmd_gap(a) -> int:
    _p({"committed": a.commit,
        "gap": _eng().detect_gap(a.type, a.description, a.missing or "", _split(a.related), _now(),
                               commit=a.commit).to_dict()})
    return 0


def _cmd_relationship(a) -> int:
    _p({"committed": a.commit,
        "relationship": _eng().connect_insights(a.source, a.target, a.relation, _now(),
                                               commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_insight_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_insight_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_insight_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)

    cx = sub.add_parser("context")
    cx.add_argument("--domain", required=True)
    cx.add_argument("--description", default="")
    cx.add_argument("--refs", default="")
    cx.add_argument("--commit", action="store_true")

    ins = sub.add_parser("insight")
    ins.add_argument("--category", required=True)
    ins.add_argument("--statement", required=True)
    ins.add_argument("--confidence", type=float, default=0.5)
    ins.add_argument("--context", default="")
    ins.add_argument("--refs", default="")
    ins.add_argument("--commit", action="store_true")

    it = sub.add_parser("interpret")
    it.add_argument("--insight", required=True)
    it.add_argument("--explanation", required=True)
    it.add_argument("--supporting", default="")
    it.add_argument("--conflicting", default="")
    it.add_argument("--source", default="")
    it.add_argument("--commit", action="store_true")

    gp = sub.add_parser("gap")
    gp.add_argument("--type", required=True)
    gp.add_argument("--description", required=True)
    gp.add_argument("--missing", default="")
    gp.add_argument("--related", default="")
    gp.add_argument("--commit", action="store_true")

    rl = sub.add_parser("relationship")
    rl.add_argument("--source", required=True)
    rl.add_argument("--target", required=True)
    rl.add_argument("--relation", required=True)
    rl.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"context": _cmd_context, "insight": _cmd_insight, "interpret": _cmd_interpret,
            "gap": _cmd_gap, "relationship": _cmd_relationship, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
