"""`python -m jarvis.research_learning <cmd>` — 연구 학습 루프 CLI. **관찰·분석·기록 전용.**

  cycle      --name [--scope]                            학습 루프 [--commit]
  observe    --loop --layer --ref --observation --verdict  관찰(OBSERVED→ANALYZED) [--commit]
  lesson     --loop --title [--lesson --category --evidence]  교훈(→LESSON_CREATED) [--commit]
  candidate  --loop --title [--desc --rationale --reviewer]  개선 후보(applied=False) [--commit]
  feedback   --loop --source --feedback [--sentiment]    피드백 [--commit]
  review     --loop                                      리뷰(→REVIEWED) [--commit]
  compare    --loop-a --loop-b --metric --value-a --value-b [--lower-better]  사이클 비교 [--commit]
  report     --loop / loops / verify / replay / summary

자동 개선·수정·실행 없음. 개선 후보는 기록만. LEARNING ≠ MODIFICATION · CANDIDATE ≠ EXECUTION.
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
    from jarvis.research_learning.engine import ResearchLearningLoopEngine
    return ResearchLearningLoopEngine()


def _cmd_cycle(a) -> int:
    _p({"committed": a.commit,
        "loop": _eng().create_learning_cycle(a.name, a.scope or "", _now(),
                                             commit=a.commit).to_dict()})
    return 0


def _cmd_observe(a) -> int:
    _p({"committed": a.commit,
        "observation": _eng().observe_research(a.loop, a.layer, a.ref, a.observation, a.verdict,
                                              _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_lesson(a) -> int:
    _p({"committed": a.commit,
        "lesson": _eng().extract_lesson(a.loop, a.title, a.lesson or "", a.category or "",
                                       a.evidence or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_candidate(a) -> int:
    _p({"committed": a.commit,
        "candidate": _eng().record_improvement_candidate(a.loop, a.title, a.desc or "",
                                                        a.rationale or "", a.reviewer or "", _now(),
                                                        commit=a.commit).to_dict(),
        "note": "applied=False — never auto-applied"})
    return 0


def _cmd_feedback(a) -> int:
    _p({"committed": a.commit,
        "feedback": _eng().record_feedback(a.loop, a.source, a.feedback, a.sentiment or "NEUTRAL",
                                          _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().review_loop(a.loop, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_compare(a) -> int:
    _p({"committed": a.commit,
        "pattern": _eng().compare_cycles(a.loop_a, a.loop_b, a.metric, a.value_a, a.value_b,
                                        not a.lower_better, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_learning_report(a.loop, "LOOP", _now(),
                                                 commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_loops(a) -> int:
    eng = _eng()
    ls = eng.list_loops()
    _p({"loops": [{"loop_id": x, "state": eng.current_state(x)} for x in ls]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_learning.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_learning.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_learning")
    sub = ap.add_subparsers(dest="cmd", required=True)

    cy = sub.add_parser("cycle")
    cy.add_argument("--name", required=True)
    cy.add_argument("--scope", default="")
    cy.add_argument("--commit", action="store_true")

    ob = sub.add_parser("observe")
    ob.add_argument("--loop", required=True)
    ob.add_argument("--layer", required=True)
    ob.add_argument("--ref", required=True)
    ob.add_argument("--observation", required=True)
    ob.add_argument("--verdict", required=True, choices=["WORKED", "FAILED", "INVESTIGATE"])
    ob.add_argument("--commit", action="store_true")

    le = sub.add_parser("lesson")
    le.add_argument("--loop", required=True)
    le.add_argument("--title", required=True)
    le.add_argument("--lesson", default="")
    le.add_argument("--category", default="")
    le.add_argument("--evidence", default="")
    le.add_argument("--commit", action="store_true")

    ca = sub.add_parser("candidate")
    ca.add_argument("--loop", required=True)
    ca.add_argument("--title", required=True)
    ca.add_argument("--desc", default="")
    ca.add_argument("--rationale", default="")
    ca.add_argument("--reviewer", default="")
    ca.add_argument("--commit", action="store_true")

    fb = sub.add_parser("feedback")
    fb.add_argument("--loop", required=True)
    fb.add_argument("--source", required=True)
    fb.add_argument("--feedback", required=True)
    fb.add_argument("--sentiment", default="NEUTRAL")
    fb.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--loop", required=True)
    rv.add_argument("--commit", action="store_true")

    cp = sub.add_parser("compare")
    cp.add_argument("--loop-a", dest="loop_a", required=True)
    cp.add_argument("--loop-b", dest="loop_b", required=True)
    cp.add_argument("--metric", required=True)
    cp.add_argument("--value-a", dest="value_a", type=float, required=True)
    cp.add_argument("--value-b", dest="value_b", type=float, required=True)
    cp.add_argument("--lower-better", dest="lower_better", action="store_true")
    cp.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--loop", required=True)
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("loops")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"cycle": _cmd_cycle, "observe": _cmd_observe, "lesson": _cmd_lesson,
            "candidate": _cmd_candidate, "feedback": _cmd_feedback, "review": _cmd_review,
            "compare": _cmd_compare, "report": _cmd_report, "loops": _cmd_loops,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
