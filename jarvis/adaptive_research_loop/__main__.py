"""`python -m jarvis.adaptive_research_loop <cmd>` — 적응 연구 루프 CLI. **개선 기록 전용.**

  cycle      --name [--mandate]                          루프 사이클 [--commit]
  feedback   --cycle --layer --ref --observation [--category]  피드백 [--commit]
  analyze    --cycle --feedback --title [--root --category]  실패 분석(OBSERVED→ANALYZED) [--commit]
  improve    --proposal --description --change            개선 제안(→PROPOSED) [--commit]
  review     --proposal --reviewer --decision             인간 리뷰(→REVIEWED) [--commit]
  outcome    --proposal --outcome [--evidence]            결과 기록(→RECORDED) [--commit]
  compare    --cycle-a --cycle-b --metric --value-a --value-b [--lower-better]  효율 비교 [--commit]
  report     --cycle / proposals [--cycle] / verify / replay / summary

실제 자동 수정·배포 없음 — 개선 기록만. IMPROVEMENT ≠ EXECUTION · PROPOSAL ≠ MODIFICATION · RECORDED ≠ DEPLOYMENT.
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
    from jarvis.adaptive_research_loop.engine import AdaptiveResearchLoopEngine
    return AdaptiveResearchLoopEngine()


def _cmd_cycle(a) -> int:
    _p({"committed": a.commit,
        "cycle": _eng().create_adaptation_cycle(a.name, a.mandate or "", _now(),
                                                commit=a.commit).to_dict()})
    return 0


def _cmd_feedback(a) -> int:
    _p({"committed": a.commit,
        "feedback": _eng().create_feedback(a.cycle, a.layer, a.ref, a.observation, a.category or "",
                                          _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_analyze(a) -> int:
    _p({"committed": a.commit,
        "proposal": _eng().analyze_failure(a.cycle, a.feedback, a.title, a.root or "",
                                          a.category or "WORKFLOW", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_improve(a) -> int:
    _p({"committed": a.commit,
        "proposal": _eng().generate_improvement(a.proposal, a.description, a.change, _now(),
                                              commit=a.commit).to_dict(),
        "note": "PROPOSAL ≠ MODIFICATION"})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "proposal": _eng().review_improvement(a.proposal, a.reviewer, a.decision, _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_outcome(a) -> int:
    _p({"committed": a.commit,
        "adaptation": _eng().record_outcome(a.proposal, a.outcome, a.evidence or "", "", _now(),
                                          commit=a.commit).to_dict(),
        "note": "RECORDED ≠ DEPLOYMENT"})
    return 0


def _cmd_compare(a) -> int:
    _p({"committed": a.commit,
        "metric": _eng().compare_cycles(a.cycle_a, a.cycle_b, a.metric, a.value_a, a.value_b,
                                       not a.lower_better, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.cycle, "CYCLE", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_proposals(a) -> int:
    eng = _eng()
    ps = eng.list_proposals(a.cycle or "")
    _p({"proposals": [{"proposal_id": p, "state": eng.current_state(p)} for p in ps]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.adaptive_research_loop.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.adaptive_research_loop.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.adaptive_research_loop")
    sub = ap.add_subparsers(dest="cmd", required=True)

    cy = sub.add_parser("cycle")
    cy.add_argument("--name", required=True)
    cy.add_argument("--mandate", default="")
    cy.add_argument("--commit", action="store_true")

    fb = sub.add_parser("feedback")
    fb.add_argument("--cycle", required=True)
    fb.add_argument("--layer", required=True)
    fb.add_argument("--ref", required=True)
    fb.add_argument("--observation", required=True)
    fb.add_argument("--category", default="")
    fb.add_argument("--commit", action="store_true")

    an = sub.add_parser("analyze")
    an.add_argument("--cycle", required=True)
    an.add_argument("--feedback", required=True)
    an.add_argument("--title", required=True)
    an.add_argument("--root", default="")
    an.add_argument("--category", default="WORKFLOW")
    an.add_argument("--commit", action="store_true")

    im = sub.add_parser("improve")
    im.add_argument("--proposal", required=True)
    im.add_argument("--description", required=True)
    im.add_argument("--change", required=True)
    im.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--proposal", required=True)
    rv.add_argument("--reviewer", required=True)
    rv.add_argument("--decision", required=True, choices=["ACCEPT", "REWORK", "NOTE"])
    rv.add_argument("--commit", action="store_true")

    oc = sub.add_parser("outcome")
    oc.add_argument("--proposal", required=True)
    oc.add_argument("--outcome", required=True)
    oc.add_argument("--evidence", default="")
    oc.add_argument("--commit", action="store_true")

    cp = sub.add_parser("compare")
    cp.add_argument("--cycle-a", dest="cycle_a", required=True)
    cp.add_argument("--cycle-b", dest="cycle_b", required=True)
    cp.add_argument("--metric", required=True)
    cp.add_argument("--value-a", dest="value_a", type=float, required=True)
    cp.add_argument("--value-b", dest="value_b", type=float, required=True)
    cp.add_argument("--lower-better", dest="lower_better", action="store_true")
    cp.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--cycle", required=True)
    rp.add_argument("--commit", action="store_true")

    ps = sub.add_parser("proposals")
    ps.add_argument("--cycle", default="")

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"cycle": _cmd_cycle, "feedback": _cmd_feedback, "analyze": _cmd_analyze,
            "improve": _cmd_improve, "review": _cmd_review, "outcome": _cmd_outcome,
            "compare": _cmd_compare, "report": _cmd_report, "proposals": _cmd_proposals,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
