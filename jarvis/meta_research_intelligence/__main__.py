"""`python -m jarvis.meta_research_intelligence <cmd>` — 메타 연구 지능 CLI. **관찰 전용.**

  metric      --name --value [--unit --dimension]          메타 지표 기록 [--commit]
  compute                                                  5개 메타 지표 산출(READ ONLY) [--commit]
  quality     --subject --dimension --score                연구 품질 평가 [--commit]
  opportunity --area --description [--evidence-count]       최적화 기회(적용 없음) [--commit]
  observation --aspect --finding                           메타 관찰 [--commit]
  report [--scope] / verify / summary / replay

자동 최적화·실행·배포·거래 없음. OBSERVATION ≠ OPTIMIZATION · OPPORTUNITY ≠ APPLIED.
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
    from jarvis.meta_research_intelligence.engine import MetaResearchIntelligenceEngine
    return MetaResearchIntelligenceEngine()


def _cmd_metric(a) -> int:
    _p({"committed": a.commit,
        "metric": _eng().record_meta_metric(a.name, a.value, a.unit or "ratio", a.dimension or "",
                                           "meta", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_compute(a) -> int:
    _p({"committed": a.commit, "meta_metrics": _eng().compute_meta_metrics(_now(), commit=a.commit),
        "note": "OBSERVATION ≠ OPTIMIZATION"})
    return 0


def _cmd_quality(a) -> int:
    _p({"committed": a.commit,
        "quality": _eng().assess_quality(a.subject, a.dimension, a.score, "", _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_opportunity(a) -> int:
    _p({"committed": a.commit,
        "opportunity": _eng().detect_opportunity(a.area, a.description,
                                               {"evidence_count": a.evidence_count}, _now(),
                                               commit=a.commit).to_dict(),
        "note": "is_applied=False"})
    return 0


def _cmd_observation(a) -> int:
    _p({"committed": a.commit,
        "observation": _eng().record_observation(a.aspect, a.finding, {}, _now(),
                                               commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.meta_research_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.meta_research_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.meta_research_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)

    me = sub.add_parser("metric")
    me.add_argument("--name", required=True)
    me.add_argument("--value", type=float, required=True)
    me.add_argument("--unit", default="ratio")
    me.add_argument("--dimension", default="")
    me.add_argument("--commit", action="store_true")

    cp = sub.add_parser("compute")
    cp.add_argument("--commit", action="store_true")

    ql = sub.add_parser("quality")
    ql.add_argument("--subject", required=True)
    ql.add_argument("--dimension", required=True)
    ql.add_argument("--score", type=float, required=True)
    ql.add_argument("--commit", action="store_true")

    op = sub.add_parser("opportunity")
    op.add_argument("--area", required=True)
    op.add_argument("--description", required=True)
    op.add_argument("--evidence-count", dest="evidence_count", type=int, default=0)
    op.add_argument("--commit", action="store_true")

    ob = sub.add_parser("observation")
    ob.add_argument("--aspect", required=True)
    ob.add_argument("--finding", required=True)
    ob.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"metric": _cmd_metric, "compute": _cmd_compute, "quality": _cmd_quality,
            "opportunity": _cmd_opportunity, "observation": _cmd_observation, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
