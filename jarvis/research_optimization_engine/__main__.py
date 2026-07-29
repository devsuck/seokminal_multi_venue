"""`python -m jarvis.research_optimization_engine <cmd>` — 연구 최적화 엔진 CLI. **분석·제안 전용.**

  study      --name [--scope]                            최적화 연구 [--commit]
  analyze    --study --subject --metric --value [--throughput]  효율 분석(→ANALYZED) [--commit]
  bottleneck --study --target --severity [--load --desc]  병목 탐지(→IDENTIFIED) [--commit]
  compare    --study --a --b --metric --value-a --value-b [--lower-better]  역사 비교 [--commit]
  propose    --study --title --problem --evidence --impact --risk --reviewer [--change]  제안(→PROPOSED) [--commit]
  review     --study                                     리뷰(→REVIEWED) [--commit]
  report     --study / studies / ranked --study / verify / replay / summary

자동 최적화·코드/설정/권한/전략 변경 없음. ANALYZE ≠ OPTIMIZE · PROPOSAL ≠ MODIFICATION · IDENTIFIED ≠ EXECUTION.
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
    from jarvis.research_optimization_engine.engine import ResearchOptimizationEngine
    return ResearchOptimizationEngine()


def _cmd_study(a) -> int:
    _p({"committed": a.commit,
        "study": _eng().create_optimization_study(a.name, a.scope or "ECOSYSTEM", _now(),
                                                 commit=a.commit).to_dict()})
    return 0


def _cmd_analyze(a) -> int:
    _p({"committed": a.commit,
        "efficiency": _eng().analyze_pipeline(a.study, a.subject, a.metric, a.value, a.throughput,
                                             "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_bottleneck(a) -> int:
    _p({"committed": a.commit,
        "bottleneck": _eng().detect_bottleneck(a.study, a.target, a.severity, a.load, a.desc or "",
                                              "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_compare(a) -> int:
    _p({"committed": a.commit,
        "comparison": _eng().compare_efficiency(a.study, a.a, a.b, a.metric, a.value_a, a.value_b,
                                              not a.lower_better, _now(),
                                              commit=a.commit).to_dict()})
    return 0


def _cmd_propose(a) -> int:
    _p({"committed": a.commit,
        "proposal": _eng().record_proposal(a.study, a.title, a.problem, a.evidence, a.impact,
                                          a.risk, a.reviewer, a.change or "", _now(),
                                          commit=a.commit).to_dict(),
        "note": "PROPOSAL ≠ MODIFICATION"})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().review_study(a.study, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.study, "STUDY", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_studies(a) -> int:
    eng = _eng()
    ss = eng.list_studies()
    _p({"studies": [{"study_id": s, "state": eng.current_state(s)} for s in ss]})
    return 0


def _cmd_ranked(a) -> int:
    _p({"ranked_bottlenecks": _eng().ranked_bottlenecks(a.study)})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_optimization_engine.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_optimization_engine.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_optimization_engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("study")
    st.add_argument("--name", required=True)
    st.add_argument("--scope", default="ECOSYSTEM")
    st.add_argument("--commit", action="store_true")

    an = sub.add_parser("analyze")
    an.add_argument("--study", required=True)
    an.add_argument("--subject", required=True)
    an.add_argument("--metric", required=True)
    an.add_argument("--value", type=float, required=True)
    an.add_argument("--throughput", type=float, default=0.0)
    an.add_argument("--commit", action="store_true")

    bn = sub.add_parser("bottleneck")
    bn.add_argument("--study", required=True)
    bn.add_argument("--target", required=True)
    bn.add_argument("--severity", required=True, choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    bn.add_argument("--load", type=float, default=0.0)
    bn.add_argument("--desc", default="")
    bn.add_argument("--commit", action="store_true")

    cp = sub.add_parser("compare")
    cp.add_argument("--study", required=True)
    cp.add_argument("--a", required=True)
    cp.add_argument("--b", required=True)
    cp.add_argument("--metric", required=True)
    cp.add_argument("--value-a", dest="value_a", type=float, required=True)
    cp.add_argument("--value-b", dest="value_b", type=float, required=True)
    cp.add_argument("--lower-better", dest="lower_better", action="store_true")
    cp.add_argument("--commit", action="store_true")

    pr = sub.add_parser("propose")
    pr.add_argument("--study", required=True)
    pr.add_argument("--title", required=True)
    pr.add_argument("--problem", required=True)
    pr.add_argument("--evidence", required=True)
    pr.add_argument("--impact", required=True)
    pr.add_argument("--risk", required=True)
    pr.add_argument("--reviewer", required=True)
    pr.add_argument("--change", default="")
    pr.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--study", required=True)
    rv.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--study", required=True)
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("studies")

    rk = sub.add_parser("ranked")
    rk.add_argument("--study", required=True)

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"study": _cmd_study, "analyze": _cmd_analyze, "bottleneck": _cmd_bottleneck,
            "compare": _cmd_compare, "propose": _cmd_propose, "review": _cmd_review,
            "report": _cmd_report, "studies": _cmd_studies, "ranked": _cmd_ranked,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
