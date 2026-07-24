"""`python -m jarvis.research_experience_memory <cmd>` — 연구 기억·경험 CLI. **기억·기록·검색 전용.**

  memory     --layer --ref --type --title [--context]    기억 등록(CREATED→RECORDED) [--commit]
  experience --memory --subject [--outcome --lesson --agent]  경험(→INDEXED) [--commit]
  failure    --memory --approach [--reason --recurrence]  실패 기억 [--commit]
  pattern    --memory --pattern [--conditions --confidence]  성공 패턴 [--commit]
  episode    --name [--desc --refs]                       에피소드 [--commit]
  retrievable --memory                                    검색가능 표시 [--commit]
  retrieve   [--query --type]                             검색(기록) [--commit]
  similar    --memory [--threshold]                       유사 경험(메타데이터) [--commit]
  summary-gen [--scope --scope-id] / lineage --episode / memories [--type] / verify / replay / summary

실행 능력 없음. MEMORY ≠ EXECUTION · SIMILARITY ≠ RECOMMENDATION · VALIDATED ≠ DEPLOYED.
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
    from jarvis.research_experience_memory.engine import ResearchExperienceMemoryEngine
    return ResearchExperienceMemoryEngine()


def _cmd_memory(a) -> int:
    _p({"committed": a.commit,
        "memory": _eng().register_memory(a.layer, a.ref, a.type, a.title, a.context or "", None,
                                        _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_experience(a) -> int:
    _p({"committed": a.commit,
        "experience": _eng().record_experience(a.memory, a.subject, a.outcome or "", a.lesson or "",
                                              a.agent or "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_failure(a) -> int:
    _p({"committed": a.commit,
        "failure": _eng().record_failure(a.memory, a.approach, a.reason or "", a.recurrence, _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_pattern(a) -> int:
    _p({"committed": a.commit,
        "pattern": _eng().record_success_pattern(a.memory, a.pattern, a.conditions or "",
                                               a.confidence, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_episode(a) -> int:
    refs = a.refs.split(",") if a.refs else []
    _p({"committed": a.commit,
        "episode": _eng().create_episode(a.name, a.desc or "", refs, _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_retrievable(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().make_retrievable(a.memory, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_retrieve(a) -> int:
    _p({"committed": a.commit,
        "retrieval": _eng().retrieve_memory(a.query or "", a.type or "", _now(),
                                           commit=a.commit).to_dict(),
        "note": "SIMILARITY ≠ RECOMMENDATION"})
    return 0


def _cmd_similar(a) -> int:
    _p({"committed": a.commit,
        "retrieval": _eng().find_similar_experience(a.memory, a.threshold, _now(),
                                                  commit=a.commit).to_dict(),
        "note": "metadata only, no recommendation"})
    return 0


def _cmd_summary_gen(a) -> int:
    _p({"committed": a.commit,
        "summary": _eng().generate_summary(a.scope or "ALL", a.scope_id or "ALL", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_lineage(a) -> int:
    arts = _eng().build_lineage(a.episode, _now(), commit=a.commit)
    _p({"committed": a.commit, "artifacts": [x.to_dict() for x in arts]})
    return 0


def _cmd_memories(a) -> int:
    eng = _eng()
    ms = eng.list_memories(a.type or "")
    _p({"memories": [{"memory_id": m, "state": eng.current_state(m)} for m in ms]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_experience_memory.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_experience_memory.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_experience_memory")
    sub = ap.add_subparsers(dest="cmd", required=True)

    me = sub.add_parser("memory")
    me.add_argument("--layer", required=True)
    me.add_argument("--ref", required=True)
    me.add_argument("--type", required=True)
    me.add_argument("--title", required=True)
    me.add_argument("--context", default="")
    me.add_argument("--commit", action="store_true")

    ex = sub.add_parser("experience")
    ex.add_argument("--memory", required=True)
    ex.add_argument("--subject", required=True)
    ex.add_argument("--outcome", default="")
    ex.add_argument("--lesson", default="")
    ex.add_argument("--agent", default="")
    ex.add_argument("--commit", action="store_true")

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

    ep = sub.add_parser("episode")
    ep.add_argument("--name", required=True)
    ep.add_argument("--desc", default="")
    ep.add_argument("--refs", default="")
    ep.add_argument("--commit", action="store_true")

    rt = sub.add_parser("retrievable")
    rt.add_argument("--memory", required=True)
    rt.add_argument("--commit", action="store_true")

    re = sub.add_parser("retrieve")
    re.add_argument("--query", default="")
    re.add_argument("--type", default="")
    re.add_argument("--commit", action="store_true")

    si = sub.add_parser("similar")
    si.add_argument("--memory", required=True)
    si.add_argument("--threshold", type=float, default=0.0)
    si.add_argument("--commit", action="store_true")

    sg = sub.add_parser("summary-gen")
    sg.add_argument("--scope", default="ALL")
    sg.add_argument("--scope-id", dest="scope_id", default="ALL")
    sg.add_argument("--commit", action="store_true")

    li = sub.add_parser("lineage")
    li.add_argument("--episode", required=True)
    li.add_argument("--commit", action="store_true")

    ms = sub.add_parser("memories")
    ms.add_argument("--type", default="")

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"memory": _cmd_memory, "experience": _cmd_experience, "failure": _cmd_failure,
            "pattern": _cmd_pattern, "episode": _cmd_episode, "retrievable": _cmd_retrievable,
            "retrieve": _cmd_retrieve, "similar": _cmd_similar, "summary-gen": _cmd_summary_gen,
            "lineage": _cmd_lineage, "memories": _cmd_memories, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
