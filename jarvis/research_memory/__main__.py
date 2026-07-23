"""`python -m jarvis.research_memory <cmd>` — 연구 기억 인텔리전스 CLI. **보존·검색·기록 전용.**

  memory  --type --source-ref --content [--importance --confidence] [--commit]
  lesson  --observation [--cause --impact --confidence] [--commit]
  connect --from-memory --relation --to-memory [--weight] [--commit]
  search  --query [--threshold --top-k] [--commit]
  cluster [--commit]
  report  [--scope --metrics-json] [--commit]
  verify / replay / summary

실제 실행·거래·배포·전략 선택·모델 수정·학습 갱신 없음 — 기억·검색·기록만.
MEMORY ≠ DECISION · RECALL ≠ APPROVAL · SIMILARITY ≠ VALIDATION.
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
    from jarvis.research_memory.engine import ResearchMemoryEngine
    return ResearchMemoryEngine()


def _cmd_memory(a) -> int:
    m = _eng().store_memory(a.type, a.source_ref, a.content, "", a.importance, a.confidence, 0,
                            "", _now(), commit=a.commit)
    _p({"committed": a.commit, "memory": m.to_dict(), "note": "MEMORY ≠ DECISION"})
    return 0


def _cmd_lesson(a) -> int:
    l = _eng().record_lesson(a.observation, a.cause or "", a.impact or "", [], a.confidence,
                             _now(), commit=a.commit)
    _p({"committed": a.commit, "lesson": l.to_dict()})
    return 0


def _cmd_connect(a) -> int:
    c = _eng().connect_memory(a.from_memory, a.relation, a.to_memory, a.weight, _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "connection": c.to_dict(), "note": "SIMILARITY ≠ VALIDATION"})
    return 0


def _cmd_search(a) -> int:
    r = _eng().search_memory(a.query, a.threshold, a.top_k, _now(), commit=a.commit)
    _p({"committed": a.commit, "retrieval": r.to_dict(), "note": "RECALL ≠ APPROVAL"})
    return 0


def _cmd_cluster(a) -> int:
    cs = _eng().cluster_memories(_now(), commit=a.commit)
    _p({"committed": a.commit, "clusters": [c.to_dict() for c in cs]})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_memory_report(a.scope or "GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_memory.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_memory.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_memory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    me = sub.add_parser("memory")
    me.add_argument("--type", required=True,
                    choices=("LESSON", "FAILURE", "PATTERN", "METHOD", "INSIGHT"))
    me.add_argument("--source-ref", required=True)
    me.add_argument("--content", required=True)
    me.add_argument("--importance", type=float, default=0.0)
    me.add_argument("--confidence", type=float, default=0.0)
    me.add_argument("--commit", action="store_true")
    le = sub.add_parser("lesson")
    le.add_argument("--observation", required=True)
    le.add_argument("--cause", default="")
    le.add_argument("--impact", default="")
    le.add_argument("--confidence", type=float, default=0.0)
    le.add_argument("--commit", action="store_true")
    co = sub.add_parser("connect")
    co.add_argument("--from-memory", required=True)
    co.add_argument("--relation", required=True,
                    choices=("SIMILAR_TO", "DERIVED_FROM", "CONTRADICTS", "SUPPORTS", "REPEATS"))
    co.add_argument("--to-memory", required=True)
    co.add_argument("--weight", type=float, default=0.0)
    co.add_argument("--commit", action="store_true")
    se = sub.add_parser("search")
    se.add_argument("--query", required=True)
    se.add_argument("--threshold", type=float, default=0.1)
    se.add_argument("--top-k", type=int, default=5)
    se.add_argument("--commit", action="store_true")
    cl = sub.add_parser("cluster")
    cl.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="GLOBAL")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"memory": _cmd_memory, "lesson": _cmd_lesson, "connect": _cmd_connect,
            "search": _cmd_search, "cluster": _cmd_cluster, "report": _cmd_report,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
