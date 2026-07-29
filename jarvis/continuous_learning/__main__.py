"""`python -m jarvis.continuous_learning <cmd>` — 연구 기억·지속 학습 CLI. **기억·검색·분석 전용.**

  memory    --type --layer --ref [--summary]        기억 등록(CREATED) [--commit]
  experiment --ref [--hypothesis --dataset --status] 실험 기억 기록 [--commit]
  failure   --type --cause [--affected]              실패 기록 [--commit]
  pattern   --type --description [--confidence]       성공 패턴 기록 [--commit]
  lesson    --lesson [--context --by]                교훈 초안(DRAFT) [--commit]
  search    [--type --source]                        기억 검색
  failures  [--type]                                 관련 실패 검색
  stats / memories / verify / replay / summary

거래·라이브 신호·모델 수정·전략 배포·자본 배분·자동 승인 없음. REMEMBER ≠ EXECUTE · CONFIDENCE ≠ APPROVAL.
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
    from jarvis.continuous_learning.engine import ContinuousLearningEngine
    return ContinuousLearningEngine()


def _cmd_memory(a) -> int:
    _p({"committed": a.commit,
        "memory": _eng().register_memory(a.type, a.layer, a.ref, a.summary or "", {}, [], _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_experiment(a) -> int:
    _p({"committed": a.commit,
        "experiment": _eng().record_experiment_memory(a.ref, a.hypothesis or "", a.dataset or "",
                                                     {}, "", a.status or "UNKNOWN", "", now=_now(),
                                                     commit=a.commit).to_dict()})
    return 0


def _cmd_failure(a) -> int:
    _p({"committed": a.commit,
        "failure": _eng().record_failure(a.type, a.cause, [], a.affected or "", now=_now(),
                                        commit=a.commit).to_dict(),
        "note": "negative knowledge preserved"})
    return 0


def _cmd_pattern(a) -> int:
    _p({"committed": a.commit,
        "pattern": _eng().record_success_pattern(a.type, a.description, [], a.confidence, now=_now(),
                                               commit=a.commit).to_dict(),
        "note": "confidence = metadata, not approval"})
    return 0


def _cmd_lesson(a) -> int:
    _p({"committed": a.commit,
        "lesson": _eng().draft_lesson(a.lesson, a.context or "", [], [], a.by or "", now=_now(),
                                     commit=a.commit).to_dict(),
        "note": "human review required to record"})
    return 0


def _cmd_search(a) -> int:
    _p({"results": _eng().search_memory(a.type, a.source, None, None, None, None, _now(),
                                       commit=False)})
    return 0


def _cmd_failures(a) -> int:
    _p({"failures": _eng().find_related_failures(a.type, None, None, _now(), commit=False)})
    return 0


def _cmd_stats(a) -> int:
    _p(_eng().learning_stats())
    return 0


def _cmd_memories(a) -> int:
    eng = _eng()
    _p({"memories": [{"memory_id": m, "state": eng.memory_state(m)} for m in eng.list_memories()]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.continuous_learning.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.continuous_learning.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.continuous_learning")
    sub = ap.add_subparsers(dest="cmd", required=True)

    mm = sub.add_parser("memory")
    mm.add_argument("--type", required=True)
    mm.add_argument("--layer", required=True)
    mm.add_argument("--ref", required=True)
    mm.add_argument("--summary", default="")
    mm.add_argument("--commit", action="store_true")

    ex = sub.add_parser("experiment")
    ex.add_argument("--ref", required=True)
    ex.add_argument("--hypothesis", default="")
    ex.add_argument("--dataset", default="")
    ex.add_argument("--status", default="UNKNOWN")
    ex.add_argument("--commit", action="store_true")

    fa = sub.add_parser("failure")
    fa.add_argument("--type", required=True)
    fa.add_argument("--cause", required=True)
    fa.add_argument("--affected", default="")
    fa.add_argument("--commit", action="store_true")

    pt = sub.add_parser("pattern")
    pt.add_argument("--type", required=True)
    pt.add_argument("--description", required=True)
    pt.add_argument("--confidence", type=float, default=0.0)
    pt.add_argument("--commit", action="store_true")

    ls = sub.add_parser("lesson")
    ls.add_argument("--lesson", required=True)
    ls.add_argument("--context", default="")
    ls.add_argument("--by", default="")
    ls.add_argument("--commit", action="store_true")

    sr = sub.add_parser("search")
    sr.add_argument("--type", default=None)
    sr.add_argument("--source", default=None)

    ff = sub.add_parser("failures")
    ff.add_argument("--type", default=None)

    sub.add_parser("stats")
    sub.add_parser("memories")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"memory": _cmd_memory, "experiment": _cmd_experiment, "failure": _cmd_failure,
            "pattern": _cmd_pattern, "lesson": _cmd_lesson, "search": _cmd_search,
            "failures": _cmd_failures, "stats": _cmd_stats, "memories": _cmd_memories,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
