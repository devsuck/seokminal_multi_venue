"""`python -m jarvis.autonomous_research_pipeline <cmd>` — 자율 연구 파이프라인 CLI. **오케스트레이션 전용.**

  pipeline   --name [--mandate]                          파이프라인 등록 [--commit]
  objective  --pipeline --title [--desc --metric --evidence]  연구 목표 [--commit]
  cycle      --objective [--iteration]                   사이클 초기화(OBJECTIVE_CREATED) [--commit]
  run        --cycle [--label --note]                    파이프라인 런 [--commit]
  advance    --cycle --to                                스테이지 전이 [--commit]
  attach     --cycle --ref-type --ref-id [--detail]      연구 참조 부착 [--commit]
  results    --cycle --result-ref [--detail]             결과 수집 [--commit]
  review     --cycle [--review-ref]                      리뷰 라우팅(→REVIEW_PENDING) [--commit]
  complete   --cycle                                     사이클 완료(→COMPLETED) [--commit]
  report     --scope-id [--scope] / state --cycle / cycles [--pipeline] / verify / replay / summary

실제 실행·배포·자본 배분·라이브 수정·모델 승인·권한 변경 없음 — 파이프라인 조정·기록만.
PIPELINE ≠ EXECUTION · STAGE ≠ DEPLOYMENT · COLLECT ≠ APPROVAL.
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
    from jarvis.autonomous_research_pipeline.engine import AutonomousResearchPipelineEngine
    return AutonomousResearchPipelineEngine()


def _cmd_pipeline(a) -> int:
    _p({"committed": a.commit,
        "pipeline": _eng().register_pipeline(a.name, a.mandate or "", _now(),
                                             commit=a.commit).to_dict()})
    return 0


def _cmd_objective(a) -> int:
    _p({"committed": a.commit,
        "objective": _eng().create_research_objective(a.pipeline, a.title, a.desc or "",
                                                      a.metric or "", a.evidence or "", _now(),
                                                      commit=a.commit).to_dict()})
    return 0


def _cmd_cycle(a) -> int:
    _p({"committed": a.commit,
        "cycle": _eng().initialize_cycle(a.objective, a.iteration, _now(),
                                         commit=a.commit).to_dict()})
    return 0


def _cmd_run(a) -> int:
    _p({"committed": a.commit,
        "run": _eng().create_pipeline_run(a.cycle, a.label or "run", a.note or "", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_advance(a) -> int:
    _p({"committed": a.commit,
        "transition": _eng().advance_stage(a.cycle, a.to, "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_attach(a) -> int:
    _p({"committed": a.commit,
        "history": _eng().attach_research_task(a.cycle, a.ref_type, a.ref_id, a.detail or "",
                                              _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_results(a) -> int:
    _p({"committed": a.commit,
        "history": _eng().collect_results(a.cycle, a.result_ref, a.detail or "", _now(),
                                         commit=a.commit).to_dict()})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "transition": _eng().trigger_review_stage(a.cycle, a.review_ref or "", _now(),
                                                 commit=a.commit).to_dict()})
    return 0


def _cmd_complete(a) -> int:
    _p({"committed": a.commit,
        "transition": _eng().complete_cycle(a.cycle, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_pipeline_report(a.scope_id, a.scope or "PIPELINE", _now(),
                                                 commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_state(a) -> int:
    _p(_eng().cycle_state_model(a.cycle))
    return 0


def _cmd_cycles(a) -> int:
    _p({"cycles": _eng().list_cycles(a.pipeline or "")})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.autonomous_research_pipeline.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.autonomous_research_pipeline.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.autonomous_research_pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("pipeline")
    pl.add_argument("--name", required=True)
    pl.add_argument("--mandate", default="")
    pl.add_argument("--commit", action="store_true")

    ob = sub.add_parser("objective")
    ob.add_argument("--pipeline", required=True)
    ob.add_argument("--title", required=True)
    ob.add_argument("--desc", default="")
    ob.add_argument("--metric", default="")
    ob.add_argument("--evidence", default="")
    ob.add_argument("--commit", action="store_true")

    cy = sub.add_parser("cycle")
    cy.add_argument("--objective", required=True)
    cy.add_argument("--iteration", type=int, default=1)
    cy.add_argument("--commit", action="store_true")

    rn = sub.add_parser("run")
    rn.add_argument("--cycle", required=True)
    rn.add_argument("--label", default="run")
    rn.add_argument("--note", default="")
    rn.add_argument("--commit", action="store_true")

    ad = sub.add_parser("advance")
    ad.add_argument("--cycle", required=True)
    ad.add_argument("--to", required=True)
    ad.add_argument("--commit", action="store_true")

    at = sub.add_parser("attach")
    at.add_argument("--cycle", required=True)
    at.add_argument("--ref-type", dest="ref_type", required=True)
    at.add_argument("--ref-id", dest="ref_id", required=True)
    at.add_argument("--detail", default="")
    at.add_argument("--commit", action="store_true")

    re = sub.add_parser("results")
    re.add_argument("--cycle", required=True)
    re.add_argument("--result-ref", dest="result_ref", required=True)
    re.add_argument("--detail", default="")
    re.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--cycle", required=True)
    rv.add_argument("--review-ref", dest="review_ref", default="")
    rv.add_argument("--commit", action="store_true")

    co = sub.add_parser("complete")
    co.add_argument("--cycle", required=True)
    co.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope-id", dest="scope_id", required=True)
    rp.add_argument("--scope", default="PIPELINE")
    rp.add_argument("--commit", action="store_true")

    stt = sub.add_parser("state")
    stt.add_argument("--cycle", required=True)

    cs = sub.add_parser("cycles")
    cs.add_argument("--pipeline", default="")

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"pipeline": _cmd_pipeline, "objective": _cmd_objective, "cycle": _cmd_cycle,
            "run": _cmd_run, "advance": _cmd_advance, "attach": _cmd_attach, "results": _cmd_results,
            "review": _cmd_review, "complete": _cmd_complete, "report": _cmd_report,
            "state": _cmd_state, "cycles": _cmd_cycles, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
