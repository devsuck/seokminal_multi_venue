"""`python -m jarvis.research_improvement <cmd>` — 연구 자기개선 루프 CLI. **분석·기록 전용.**

  registry   --name [--mandate]                              레지스트리 등록 [--commit]
  cycle      --registry --name [--scope --iteration]         연구 사이클 기록 [--commit]
  observe    --cycle --subject --metric --value [--unit --layer --ref --note]  관측 [--commit]
  metric     --cycle --metric --value [--category]           프로세스 메트릭 [--commit]
  failure    --cycle --type --subject --desc [--occurrences --layer --ref]  실패 패턴 [--commit]
  identify   --cycle --category --title [--desc]             개선 기회 식별(OBSERVED) [--commit]
  propose    --improvement --change [--rationale]            제안(→PROPOSED) [--commit]
  review     --improvement --reviewer --decision [--rationale]  리뷰(ACCEPT/REWORK/NOTE) [--commit]
  archive    --improvement                                   보관(→ARCHIVED) [--commit]
  learn      --cycle --lesson [--category --layer --ref --parent]  학습 기록 [--commit]
  compare    --cycle-a --cycle-b --metric [--lower-better]   반복 비교
  report     --cycle [--scope]                               개선 리포트 [--commit]
  cycles / improvements --cycle / verify / replay / summary

실제 실행·승인·연구/전략/모델 수정·배포·설정 변경 없음 — 개선 기록·분석만.
IMPROVEMENT ≠ EXECUTION · ACCEPTED ≠ DEPLOYMENT · PROPOSAL ≠ APPROVAL.
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
    from jarvis.research_improvement.engine import ResearchImprovementEngine
    return ResearchImprovementEngine()


def _cmd_registry(a) -> int:
    _p({"committed": a.commit,
        "registry": _eng().register_registry(a.name, a.mandate or "", _now(),
                                              commit=a.commit).to_dict()})
    return 0


def _cmd_cycle(a) -> int:
    _p({"committed": a.commit,
        "cycle": _eng().register_cycle(a.registry, a.name, a.scope or "", a.iteration, _now(),
                                       commit=a.commit).to_dict()})
    return 0


def _cmd_observe(a) -> int:
    _p({"committed": a.commit,
        "observation": _eng().record_observation(a.cycle, a.subject, a.metric, a.value, a.unit or "",
                                                  a.layer or "", a.ref or "", a.note or "", _now(),
                                                  commit=a.commit).to_dict()})
    return 0


def _cmd_metric(a) -> int:
    _p({"committed": a.commit,
        "metric": _eng().record_metric(a.cycle, a.metric, a.value, a.category or "", _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_failure(a) -> int:
    _p({"committed": a.commit,
        "failure": _eng().analyze_failure_pattern(a.cycle, a.type, a.subject, a.desc or "",
                                                   a.occurrences, a.layer or "", a.ref or "", None,
                                                   _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_identify(a) -> int:
    _p({"committed": a.commit,
        "improvement": _eng().identify_improvement(a.cycle, a.category, a.title, a.desc or "",
                                                    _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_propose(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().create_proposal(a.improvement, a.change, a.rationale or "", _now(),
                                         commit=a.commit).to_dict(),
        "note": "PROPOSAL ≠ APPROVAL"})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "review": _eng().review_improvement(a.improvement, a.reviewer, a.decision, a.rationale or "",
                                            _now(), commit=a.commit).to_dict(),
        "note": "ACCEPTED = process only, NOT deployment"})
    return 0


def _cmd_archive(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().archive_improvement(a.improvement, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_learn(a) -> int:
    _p({"committed": a.commit,
        "learning": _eng().record_learning(a.cycle, a.lesson, a.category or "", a.layer or "",
                                            a.ref or "", a.parent or "", _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_compare(a) -> int:
    _p({"committed": a.commit,
        "iteration": _eng().compare_iterations(a.cycle_a, a.cycle_b, a.metric,
                                                not a.lower_better, _now(),
                                                commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.cycle, a.scope or "CYCLE", _now(),
                                          commit=a.commit).to_dict(),
        "note": "is_binding=False · process_acceptance_only=True"})
    return 0


def _cmd_cycles(a) -> int:
    _p({"cycles": _eng().list_cycles(a.registry or "")})
    return 0


def _cmd_improvements(a) -> int:
    eng = _eng()
    imps = eng.improvements_of(a.cycle)
    _p({"improvements": [{"improvement_id": i, "state": eng.current_state(i)} for i in imps]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_improvement.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_improvement.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_improvement")
    sub = ap.add_subparsers(dest="cmd", required=True)

    rg = sub.add_parser("registry")
    rg.add_argument("--name", required=True)
    rg.add_argument("--mandate", default="")
    rg.add_argument("--commit", action="store_true")

    cy = sub.add_parser("cycle")
    cy.add_argument("--registry", required=True)
    cy.add_argument("--name", required=True)
    cy.add_argument("--scope", default="")
    cy.add_argument("--iteration", type=int, default=1)
    cy.add_argument("--commit", action="store_true")

    ob = sub.add_parser("observe")
    ob.add_argument("--cycle", required=True)
    ob.add_argument("--subject", required=True)
    ob.add_argument("--metric", required=True)
    ob.add_argument("--value", type=float, required=True)
    ob.add_argument("--unit", default="")
    ob.add_argument("--layer", default="")
    ob.add_argument("--ref", default="")
    ob.add_argument("--note", default="")
    ob.add_argument("--commit", action="store_true")

    mt = sub.add_parser("metric")
    mt.add_argument("--cycle", required=True)
    mt.add_argument("--metric", required=True)
    mt.add_argument("--value", type=float, required=True)
    mt.add_argument("--category", default="")
    mt.add_argument("--commit", action="store_true")

    fa = sub.add_parser("failure")
    fa.add_argument("--cycle", required=True)
    fa.add_argument("--type", required=True)
    fa.add_argument("--subject", required=True)
    fa.add_argument("--desc", default="")
    fa.add_argument("--occurrences", type=int, default=1)
    fa.add_argument("--layer", default="")
    fa.add_argument("--ref", default="")
    fa.add_argument("--commit", action="store_true")

    idn = sub.add_parser("identify")
    idn.add_argument("--cycle", required=True)
    idn.add_argument("--category", required=True)
    idn.add_argument("--title", required=True)
    idn.add_argument("--desc", default="")
    idn.add_argument("--commit", action="store_true")

    pr = sub.add_parser("propose")
    pr.add_argument("--improvement", required=True)
    pr.add_argument("--change", required=True)
    pr.add_argument("--rationale", default="")
    pr.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--improvement", required=True)
    rv.add_argument("--reviewer", required=True)
    rv.add_argument("--decision", required=True, choices=["ACCEPT", "REWORK", "NOTE"])
    rv.add_argument("--rationale", default="")
    rv.add_argument("--commit", action="store_true")

    ar = sub.add_parser("archive")
    ar.add_argument("--improvement", required=True)
    ar.add_argument("--commit", action="store_true")

    ln = sub.add_parser("learn")
    ln.add_argument("--cycle", required=True)
    ln.add_argument("--lesson", required=True)
    ln.add_argument("--category", default="")
    ln.add_argument("--layer", default="")
    ln.add_argument("--ref", default="")
    ln.add_argument("--parent", default="")
    ln.add_argument("--commit", action="store_true")

    cp = sub.add_parser("compare")
    cp.add_argument("--cycle-a", dest="cycle_a", required=True)
    cp.add_argument("--cycle-b", dest="cycle_b", required=True)
    cp.add_argument("--metric", required=True)
    cp.add_argument("--lower-better", dest="lower_better", action="store_true")
    cp.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--cycle", required=True)
    rp.add_argument("--scope", default="CYCLE")
    rp.add_argument("--commit", action="store_true")

    cs = sub.add_parser("cycles")
    cs.add_argument("--registry", default="")

    im = sub.add_parser("improvements")
    im.add_argument("--cycle", required=True)

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"registry": _cmd_registry, "cycle": _cmd_cycle, "observe": _cmd_observe,
            "metric": _cmd_metric, "failure": _cmd_failure, "identify": _cmd_identify,
            "propose": _cmd_propose, "review": _cmd_review, "archive": _cmd_archive,
            "learn": _cmd_learn, "compare": _cmd_compare, "report": _cmd_report,
            "cycles": _cmd_cycles, "improvements": _cmd_improvements, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
