"""`python -m jarvis.knowledge_intelligence <cmd>` — 상위 지식 인텔리전스 CLI. **분석·기록 전용.**

  similarity  --ref-a --tokens-a t1,t2 --ref-b --tokens-b t1,t3 [--commit]
  cluster     --items-json '[["a",["t1"]],["b",["t1"]]]' [--min-shared] [--commit]
  contradict  --claims-json '[{"ref":"a","subject":"s","stance":"SUPPORTS"}]' [--commit]
  failures    [--source-layer] [--commit]
  recommend   --subject --content [--reference --confidence] [--commit]
  report      [--metrics-json] [--commit]
  verify / replay / summary

실제 자동 선택·승인·배포 없음 — 유사도·클러스터·모순·패턴·추천 분석·기록만.
RECOMMENDATION ≠ ACTION · SIMILARITY ≠ SELECTION · CLUSTER ≠ APPROVAL · INSIGHT ≠ DEPLOYMENT.
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
    from jarvis.knowledge_intelligence.engine import KnowledgeIntelligenceEngine
    return KnowledgeIntelligenceEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_similarity(a) -> int:
    s = _eng().research_similarity(a.ref_a, _split(a.tokens_a), a.ref_b, _split(a.tokens_b),
                                   "jaccard", _now(), commit=a.commit)
    _p({"committed": a.commit, "similarity": s.to_dict(), "note": "SIMILARITY ≠ SELECTION"})
    return 0


def _cmd_cluster(a) -> int:
    items = [(x[0], x[1]) for x in json.loads(a.items_json)] if a.items_json else []
    cs = _eng().strategy_family_clustering(items, a.min_shared or 1, _now(), commit=a.commit)
    _p({"committed": a.commit, "clusters": [c.to_dict() for c in cs], "note": "CLUSTER ≠ APPROVAL"})
    return 0


def _cmd_contradict(a) -> int:
    claims = json.loads(a.claims_json) if a.claims_json else []
    cs = _eng().contradiction_detection(claims, _now(), commit=a.commit)
    _p({"committed": a.commit, "contradictions": [c.to_dict() for c in cs]})
    return 0


def _cmd_failures(a) -> int:
    refs = _eng().failed_experiment_retrieval(a.source_layer or "governance_memory",
                                              now=_now(), commit=a.commit)
    _p({"committed": a.commit, "failed_experiments": refs})
    return 0


def _cmd_recommend(a) -> int:
    i = _eng().knowledge_recommendation(a.subject, a.content, a.reference or "", [],
                                        a.confidence or 0.0, _now(), commit=a.commit)
    _p({"committed": a.commit, "recommendation": i.to_dict(), "note": "RECOMMENDATION ≠ ACTION"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.knowledge_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.knowledge_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.knowledge_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    si = sub.add_parser("similarity")
    si.add_argument("--ref-a", required=True)
    si.add_argument("--tokens-a", default="")
    si.add_argument("--ref-b", required=True)
    si.add_argument("--tokens-b", default="")
    si.add_argument("--commit", action="store_true")
    cl = sub.add_parser("cluster")
    cl.add_argument("--items-json", required=True)
    cl.add_argument("--min-shared", type=int, default=1)
    cl.add_argument("--commit", action="store_true")
    co = sub.add_parser("contradict")
    co.add_argument("--claims-json", required=True)
    co.add_argument("--commit", action="store_true")
    fa = sub.add_parser("failures")
    fa.add_argument("--source-layer", default="governance_memory")
    fa.add_argument("--commit", action="store_true")
    re = sub.add_parser("recommend")
    re.add_argument("--subject", required=True)
    re.add_argument("--content", required=True)
    re.add_argument("--reference", default="")
    re.add_argument("--confidence", type=float, default=0.0)
    re.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"similarity": _cmd_similarity, "cluster": _cmd_cluster, "contradict": _cmd_contradict,
            "failures": _cmd_failures, "recommend": _cmd_recommend, "report": _cmd_report,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
