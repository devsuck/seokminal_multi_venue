"""`python -m jarvis.autonomous_research_evaluation <cmd>` — 자율 연구 평가 CLI. **평가·기록 전용.**

  metric     --name --dimension [--weight --desc]         평가 기준 [--commit]
  evaluate   --layer --ref                                평가 시작(CREATED→EVALUATING) [--commit]
  score      --evaluation --dimension --score [--evidence --rationale]  차원 점수 [--commit]
  finalize   --evaluation                                 점수 확정(→SCORED) [--commit]
  review     --evaluation [--reviewer]                    리뷰(→REVIEWED) [--commit]
  compare    --eval-a --eval-b [--metric]                 벤치마크 비교 [--commit]
  report     [--scope-id --scope] / scores --evaluation / verify / replay / summary

점수는 승인·배포 권한이 아님. SCORE ≠ APPROVAL · SCORE ≠ DEPLOYMENT PERMISSION · EVALUATION ≠ SELECTION.
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
    from jarvis.autonomous_research_evaluation.engine import AutonomousResearchEvaluationEngine
    return AutonomousResearchEvaluationEngine()


def _cmd_metric(a) -> int:
    _p({"committed": a.commit,
        "criterion": _eng().define_metric(a.name, a.dimension, a.weight, a.desc or "", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_evaluate(a) -> int:
    _p({"committed": a.commit,
        "evaluation": _eng().evaluate_cycle(a.layer, a.ref, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_score(a) -> int:
    _p({"committed": a.commit,
        "score": _eng().score_quality(a.evaluation, a.dimension, a.score, a.evidence or "",
                                      a.rationale or "", _now(), commit=a.commit).to_dict(),
        "note": "SCORE ≠ APPROVAL"})
    return 0


def _cmd_finalize(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().finalize_scoring(a.evaluation, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().review_evaluation(a.evaluation, a.reviewer or "", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_compare(a) -> int:
    _p({"committed": a.commit,
        "benchmark": _eng().compare_research(a.eval_a, a.eval_b, a.metric or "overall", _now(),
                                            commit=a.commit).to_dict(),
        "note": "SCORE ≠ SELECTION"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_quality_report(a.scope_id or "ALL", a.scope or "ALL", _now(),
                                                commit=a.commit).to_dict(),
        "note": "is_approval=False · is_binding=False"})
    return 0


def _cmd_scores(a) -> int:
    _p({"scores": _eng().dimension_scores(a.evaluation)})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.autonomous_research_evaluation.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.autonomous_research_evaluation.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.autonomous_research_evaluation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    mt = sub.add_parser("metric")
    mt.add_argument("--name", required=True)
    mt.add_argument("--dimension", required=True)
    mt.add_argument("--weight", type=float, default=1.0)
    mt.add_argument("--desc", default="")
    mt.add_argument("--commit", action="store_true")

    ev = sub.add_parser("evaluate")
    ev.add_argument("--layer", required=True)
    ev.add_argument("--ref", required=True)
    ev.add_argument("--commit", action="store_true")

    sc = sub.add_parser("score")
    sc.add_argument("--evaluation", required=True)
    sc.add_argument("--dimension", required=True)
    sc.add_argument("--score", type=float, required=True)
    sc.add_argument("--evidence", default="")
    sc.add_argument("--rationale", default="")
    sc.add_argument("--commit", action="store_true")

    fi = sub.add_parser("finalize")
    fi.add_argument("--evaluation", required=True)
    fi.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--evaluation", required=True)
    rv.add_argument("--reviewer", default="")
    rv.add_argument("--commit", action="store_true")

    cp = sub.add_parser("compare")
    cp.add_argument("--eval-a", dest="eval_a", required=True)
    cp.add_argument("--eval-b", dest="eval_b", required=True)
    cp.add_argument("--metric", default="overall")
    cp.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope-id", dest="scope_id", default="ALL")
    rp.add_argument("--scope", default="ALL")
    rp.add_argument("--commit", action="store_true")

    ss = sub.add_parser("scores")
    ss.add_argument("--evaluation", required=True)

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"metric": _cmd_metric, "evaluate": _cmd_evaluate, "score": _cmd_score,
            "finalize": _cmd_finalize, "review": _cmd_review, "compare": _cmd_compare,
            "report": _cmd_report, "scores": _cmd_scores, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
