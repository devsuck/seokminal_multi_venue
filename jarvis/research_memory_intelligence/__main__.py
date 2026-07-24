"""`python -m jarvis.research_memory_intelligence <cmd>` — 연구 메모리 지능 CLI. **지식 메모리 전용.**

  memory    --source --category --content [--importance]   메모리 등록(CREATED) [--commit]
  lesson    --origin --lesson [--impact]                   교훈 기록 [--commit]
  pattern   --type --signature [--occurrences --confidence]  패턴 기록 [--commit]
  evolution --memory --change [--reason --related]         진화 이벤트(추가전용) [--commit]
  retrieve  --query [--top-k]                              컨텍스트 검색(참조만) [--commit]
  report [--scope] / verify / summary / replay

거래 결정·전략 배포·실험 실행·모델 수정·연구 산출 승인·자본 배분 없음. MEMORY ASSISTS RESEARCH · MEMORY DOES NOT DECIDE.
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
    from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
    return ResearchMemoryIntelligenceEngine()


def _cmd_memory(a) -> int:
    _p({"committed": a.commit,
        "memory": _eng().register_memory(a.source, a.category, a.content, a.importance, _now(),
                                        commit=a.commit).to_dict(),
        "note": "content immutable · MEMORY DOES NOT DECIDE"})
    return 0


def _cmd_lesson(a) -> int:
    _p({"committed": a.commit,
        "lesson": _eng().record_lesson(a.origin, a.lesson, {}, a.impact or "", _now(),
                                      commit=a.commit).to_dict()})
    return 0


def _cmd_pattern(a) -> int:
    _p({"committed": a.commit,
        "pattern": _eng().store_pattern(a.type, a.signature, a.occurrences, a.confidence, _now(),
                                      commit=a.commit).to_dict()})
    return 0


def _cmd_evolution(a) -> int:
    _p({"committed": a.commit,
        "evolution": _eng().evolve_memory(a.memory, a.change, a.reason or "", a.related or "",
                                        _now(), commit=a.commit).to_dict(),
        "note": "append-only · never mutate old memory"})
    return 0


def _cmd_retrieve(a) -> int:
    _p({"committed": a.commit,
        "retrieval": _eng().retrieve_context(a.query, a.top_k, _now(), commit=a.commit).to_dict(),
        "note": "is_recommendation=False · references only"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_memory_intelligence.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_memory_intelligence.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_memory_intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)

    me = sub.add_parser("memory")
    me.add_argument("--source", required=True)
    me.add_argument("--category", required=True)
    me.add_argument("--content", required=True)
    me.add_argument("--importance", type=float, default=0.5)
    me.add_argument("--commit", action="store_true")

    le = sub.add_parser("lesson")
    le.add_argument("--origin", required=True)
    le.add_argument("--lesson", required=True)
    le.add_argument("--impact", default="")
    le.add_argument("--commit", action="store_true")

    pa = sub.add_parser("pattern")
    pa.add_argument("--type", required=True)
    pa.add_argument("--signature", required=True)
    pa.add_argument("--occurrences", type=int, default=1)
    pa.add_argument("--confidence", type=float, default=0.5)
    pa.add_argument("--commit", action="store_true")

    ev = sub.add_parser("evolution")
    ev.add_argument("--memory", required=True)
    ev.add_argument("--change", required=True)
    ev.add_argument("--reason", default="")
    ev.add_argument("--related", default="")
    ev.add_argument("--commit", action="store_true")

    rt = sub.add_parser("retrieve")
    rt.add_argument("--query", required=True)
    rt.add_argument("--top-k", dest="top_k", type=int, default=5)
    rt.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"memory": _cmd_memory, "lesson": _cmd_lesson, "pattern": _cmd_pattern,
            "evolution": _cmd_evolution, "retrieve": _cmd_retrieve, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
