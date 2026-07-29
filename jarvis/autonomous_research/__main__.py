"""`python -m jarvis.autonomous_research <cmd>` — 자율 연구 루프 CLI. **연구 지능 전용.**

  cycle       --objective [--refs]                          연구 사이클 생성(CREATED) [--commit]
  opportunity --cycle --pattern --desc [--evidence-count]   기회 탐지(점수만) [--commit]
  proposal    --cycle --hypothesis [--risk --expected]      가설 제안(DRAFT) [--commit]
  plan        --proposal [--datasets --metrics]             실험 계획(실행 없음) [--commit]
  feedback    --cycle --summary [--future]                  학습 피드백 [--commit]
  learning    --cycle --kind --pattern                      학습 이벤트 [--commit]
  report [--scope] / verify / summary / replay

실험 자동 실행·전략 배포·모델 승인·거래·자본 배분·프로덕션 수정 없음. KNOWLEDGE ≠ TRADING · PROPOSAL ≠ APPROVAL.
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
    from jarvis.autonomous_research.engine import AutonomousResearchEngine
    return AutonomousResearchEngine()


def _split(s):
    return [x for x in (s or "").split("|") if x]


def _cmd_cycle(a) -> int:
    _p({"committed": a.commit,
        "cycle": _eng().create_cycle(a.objective, _split(a.refs), _now(),
                                    commit=a.commit).to_dict(),
        "note": "KNOWLEDGE ≠ TRADING"})
    return 0


def _cmd_opportunity(a) -> int:
    _p({"committed": a.commit,
        "opportunity": _eng().discover_opportunity(
            a.cycle, a.pattern, a.desc, {"evidence_count": a.evidence_count}, 1.0, _now(),
            commit=a.commit).to_dict(),
        "note": "is_auto_selected=False · score only"})
    return 0


def _cmd_proposal(a) -> int:
    _p({"committed": a.commit,
        "proposal": _eng().create_hypothesis(a.cycle, a.hypothesis, a.expected or "", a.risk or "MEDIUM",
                                            _split(a.validation), "", _now(), commit=a.commit).to_dict(),
        "note": "human review required for ACCEPTED"})
    return 0


def _cmd_plan(a) -> int:
    _p({"committed": a.commit,
        "plan": _eng().generate_plan(a.proposal, _split(a.datasets), _split(a.features),
                                   _split(a.validation), _split(a.metrics), _now(),
                                   commit=a.commit).to_dict(),
        "note": "is_executable=False"})
    return 0


def _cmd_feedback(a) -> int:
    _p({"committed": a.commit,
        "feedback": _eng().record_feedback(a.cycle, a.summary, _split(a.lessons), a.future or "",
                                          _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_learning(a) -> int:
    _p({"committed": a.commit,
        "learning": _eng().update_learning_history(a.cycle, a.kind, a.pattern, {}, _now(),
                                                  commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.autonomous_research.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.autonomous_research.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.autonomous_research")
    sub = ap.add_subparsers(dest="cmd", required=True)

    cy = sub.add_parser("cycle")
    cy.add_argument("--objective", required=True)
    cy.add_argument("--refs", default="")
    cy.add_argument("--commit", action="store_true")

    op = sub.add_parser("opportunity")
    op.add_argument("--cycle", required=True)
    op.add_argument("--pattern", required=True)
    op.add_argument("--desc", required=True)
    op.add_argument("--evidence-count", dest="evidence_count", type=int, default=0)
    op.add_argument("--commit", action="store_true")

    pr = sub.add_parser("proposal")
    pr.add_argument("--cycle", required=True)
    pr.add_argument("--hypothesis", required=True)
    pr.add_argument("--expected", default="")
    pr.add_argument("--risk", default="MEDIUM")
    pr.add_argument("--validation", default="")
    pr.add_argument("--commit", action="store_true")

    pl = sub.add_parser("plan")
    pl.add_argument("--proposal", required=True)
    pl.add_argument("--datasets", default="")
    pl.add_argument("--features", default="")
    pl.add_argument("--validation", default="")
    pl.add_argument("--metrics", default="")
    pl.add_argument("--commit", action="store_true")

    fb = sub.add_parser("feedback")
    fb.add_argument("--cycle", required=True)
    fb.add_argument("--summary", required=True)
    fb.add_argument("--lessons", default="")
    fb.add_argument("--future", default="")
    fb.add_argument("--commit", action="store_true")

    le = sub.add_parser("learning")
    le.add_argument("--cycle", required=True)
    le.add_argument("--kind", required=True)
    le.add_argument("--pattern", required=True)
    le.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"cycle": _cmd_cycle, "opportunity": _cmd_opportunity, "proposal": _cmd_proposal,
            "plan": _cmd_plan, "feedback": _cmd_feedback, "learning": _cmd_learning,
            "report": _cmd_report, "verify": _cmd_verify, "summary": _cmd_summary,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
