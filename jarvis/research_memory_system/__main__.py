"""`python -m jarvis.research_memory_system <cmd>` — 장기 연구 기억 CLI. **기억 시스템 전용.**

  memory     --layer --source-id --type --title [--context --evidence]   기억 생성(CREATED) [--commit]
  context    --memory --key [--data]                       연구 맥락(→INDEXED) [--commit]
  knowledge  --memory --summary [--tags --reusable]        지식 엔트리 [--commit]
  experiment --memory --ref [--outcome]                    실험 기억 [--commit]
  failure    --memory --approach [--reason --recurrence]   실패 기억 [--commit]
  pattern    --memory --pattern [--conditions --confidence]  성공 패턴 [--commit]
  link       --memory-a --memory-b [--relation]            기억 연관(→CONNECTED) [--commit]
  retrievable --memory                                     검색가능 표시 [--commit]
  search     --query [--mode --target --threshold]         기억 검색(기록) [--commit]
  snapshot   [--scope] / report [--scope] / memories [--type] / compare --a --b / verify / replay / summary

실제 실행·수정·승인·배포·권한/설정 변경 없음 — 기억 저장·검색·분석만.
MEMORY ≠ EXECUTION · RECALL ≠ APPROVAL · PATTERN ≠ DEPLOYMENT.
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
    from jarvis.research_memory_system.engine import ResearchMemorySystemEngine
    return ResearchMemorySystemEngine()


def _cmd_memory(a) -> int:
    _p({"committed": a.commit,
        "memory": _eng().register_memory(a.layer, a.source_id, a.type, a.title, a.context or "",
                                         a.evidence or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_context(a) -> int:
    _p({"committed": a.commit,
        "context": _eng().store_research_context(a.memory, a.key, a.data or "", _now(),
                                                 commit=a.commit).to_dict()})
    return 0


def _cmd_knowledge(a) -> int:
    tags = a.tags.split(",") if a.tags else []
    _p({"committed": a.commit,
        "knowledge": _eng().record_knowledge_entry(a.memory, a.summary, tags, not a.not_reusable,
                                                   _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_experiment(a) -> int:
    _p({"committed": a.commit,
        "experiment": _eng().record_experiment_memory(a.memory, a.ref, a.outcome or "", None, "", "",
                                                      _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_failure(a) -> int:
    _p({"committed": a.commit,
        "failure": _eng().record_failure_memory(a.memory, a.approach, a.reason or "", a.recurrence,
                                                "", "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_pattern(a) -> int:
    _p({"committed": a.commit,
        "pattern": _eng().record_success_pattern(a.memory, a.pattern, a.conditions or "",
                                                a.confidence, _now(), commit=a.commit).to_dict(),
        "note": "confidence is recorded value, NOT approval"})
    return 0


def _cmd_link(a) -> int:
    _p({"committed": a.commit,
        "association": _eng().link_related_memories(a.memory_a, a.memory_b, a.relation or "RELATED",
                                                   "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_retrievable(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().mark_retrievable(a.memory, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_search(a) -> int:
    _p({"committed": a.commit,
        "search": _eng().search_memory(a.query, a.mode, a.target or "", a.threshold, _now(),
                                       commit=a.commit).to_dict()})
    return 0


def _cmd_snapshot(a) -> int:
    _p({"committed": a.commit,
        "snapshot": _eng().build_memory_snapshot(a.scope or "ALL", _now(),
                                                commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_memory_report(a.scope or "ALL", _now(),
                                                commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_memories(a) -> int:
    eng = _eng()
    mems = eng.list_memories(a.type or "")
    _p({"memories": [{"memory_id": m, "state": eng.current_state(m)} for m in mems]})
    return 0


def _cmd_compare(a) -> int:
    _p(_eng().compare_memories(a.a, a.b))
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_memory_system.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_memory_system.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_memory_system")
    sub = ap.add_subparsers(dest="cmd", required=True)

    me = sub.add_parser("memory")
    me.add_argument("--layer", required=True)
    me.add_argument("--source-id", dest="source_id", required=True)
    me.add_argument("--type", required=True)
    me.add_argument("--title", required=True)
    me.add_argument("--context", default="")
    me.add_argument("--evidence", default="")
    me.add_argument("--commit", action="store_true")

    cx = sub.add_parser("context")
    cx.add_argument("--memory", required=True)
    cx.add_argument("--key", required=True)
    cx.add_argument("--data", default="")
    cx.add_argument("--commit", action="store_true")

    kn = sub.add_parser("knowledge")
    kn.add_argument("--memory", required=True)
    kn.add_argument("--summary", required=True)
    kn.add_argument("--tags", default="")
    kn.add_argument("--not-reusable", dest="not_reusable", action="store_true")
    kn.add_argument("--commit", action="store_true")

    xp = sub.add_parser("experiment")
    xp.add_argument("--memory", required=True)
    xp.add_argument("--ref", required=True)
    xp.add_argument("--outcome", default="")
    xp.add_argument("--commit", action="store_true")

    fa = sub.add_parser("failure")
    fa.add_argument("--memory", required=True)
    fa.add_argument("--approach", required=True)
    fa.add_argument("--reason", default="")
    fa.add_argument("--recurrence", type=int, default=1)
    fa.add_argument("--commit", action="store_true")

    pa = sub.add_parser("pattern")
    pa.add_argument("--memory", required=True)
    pa.add_argument("--pattern", required=True)
    pa.add_argument("--conditions", default="")
    pa.add_argument("--confidence", type=float, default=0.0)
    pa.add_argument("--commit", action="store_true")

    li = sub.add_parser("link")
    li.add_argument("--memory-a", dest="memory_a", required=True)
    li.add_argument("--memory-b", dest="memory_b", required=True)
    li.add_argument("--relation", default="RELATED")
    li.add_argument("--commit", action="store_true")

    rt = sub.add_parser("retrievable")
    rt.add_argument("--memory", required=True)
    rt.add_argument("--commit", action="store_true")

    se = sub.add_parser("search")
    se.add_argument("--query", required=True)
    se.add_argument("--mode", default="SIMILARITY",
                    choices=["EXACT", "SIMILARITY", "LINEAGE", "RELATED", "HISTORICAL"])
    se.add_argument("--target", default="")
    se.add_argument("--threshold", type=float, default=0.0)
    se.add_argument("--commit", action="store_true")

    sn = sub.add_parser("snapshot")
    sn.add_argument("--scope", default="ALL")
    sn.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="ALL")
    rp.add_argument("--commit", action="store_true")

    ms = sub.add_parser("memories")
    ms.add_argument("--type", default="")

    cp = sub.add_parser("compare")
    cp.add_argument("--a", required=True)
    cp.add_argument("--b", required=True)

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"memory": _cmd_memory, "context": _cmd_context, "knowledge": _cmd_knowledge,
            "experiment": _cmd_experiment, "failure": _cmd_failure, "pattern": _cmd_pattern,
            "link": _cmd_link, "retrievable": _cmd_retrievable, "search": _cmd_search,
            "snapshot": _cmd_snapshot, "report": _cmd_report, "memories": _cmd_memories,
            "compare": _cmd_compare, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
