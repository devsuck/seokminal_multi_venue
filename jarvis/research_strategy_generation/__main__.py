"""`python -m jarvis.research_strategy_generation <cmd>` — 연구 전략 생성 CLI. **생성 전용.**

  session   --objective                                    생성 세션(CREATED) [--commit]
  candidate --session --category --statement               후보 생성(PROPOSED, 선택 없음) [--commit]
  hypothesis --candidate --hypothesis [--rationale]        가설 기록 [--commit]
  novelty   --candidate                                    신규성 분석 [--commit]
  evidence  --candidate --ref --type                       증거 기록 [--commit]
  report [--scope] / verify / summary / replay

선택·승인·배포·실행·거래·자본 배분 없음. GENERATED ≠ SELECTED · CANDIDATE ≠ STRATEGY.
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
    from jarvis.research_strategy_generation.engine import ResearchStrategyGenerationEngine
    return ResearchStrategyGenerationEngine()


def _split(s):
    return [x for x in (s or "").split("|") if x]


def _cmd_session(a) -> int:
    _p({"committed": a.commit,
        "session": _eng().create_session(a.objective, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_candidate(a) -> int:
    _p({"committed": a.commit,
        "candidate": _eng().generate_candidate(a.session, a.category, a.statement, _split(a.refs),
                                              _now(), commit=a.commit).to_dict(),
        "note": "is_selected=False · GENERATED ≠ SELECTED"})
    return 0


def _cmd_hypothesis(a) -> int:
    _p({"committed": a.commit,
        "hypothesis": _eng().record_hypothesis(a.candidate, a.hypothesis, a.rationale or "", "",
                                             _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_novelty(a) -> int:
    _p({"committed": a.commit,
        "novelty": _eng().analyze_novelty(a.candidate, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_evidence(a) -> int:
    _p({"committed": a.commit,
        "evidence": _eng().record_evidence(a.candidate, a.ref, a.type, a.source or "", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_strategy_generation.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_strategy_generation.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_strategy_generation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    se = sub.add_parser("session")
    se.add_argument("--objective", required=True)
    se.add_argument("--commit", action="store_true")

    ca = sub.add_parser("candidate")
    ca.add_argument("--session", required=True)
    ca.add_argument("--category", required=True)
    ca.add_argument("--statement", required=True)
    ca.add_argument("--refs", default="")
    ca.add_argument("--commit", action="store_true")

    hy = sub.add_parser("hypothesis")
    hy.add_argument("--candidate", required=True)
    hy.add_argument("--hypothesis", required=True)
    hy.add_argument("--rationale", default="")
    hy.add_argument("--commit", action="store_true")

    nv = sub.add_parser("novelty")
    nv.add_argument("--candidate", required=True)
    nv.add_argument("--commit", action="store_true")

    ev = sub.add_parser("evidence")
    ev.add_argument("--candidate", required=True)
    ev.add_argument("--ref", required=True)
    ev.add_argument("--type", required=True)
    ev.add_argument("--source", default="")
    ev.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"session": _cmd_session, "candidate": _cmd_candidate, "hypothesis": _cmd_hypothesis,
            "novelty": _cmd_novelty, "evidence": _cmd_evidence, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
