"""`python -m jarvis.knowledge_sharing <cmd>` — 에이전트 간 지식 공유 CLI. **공유·기록 전용.**

  registry  --name [--mandate]                          레지스트리 등록 [--commit]
  topic     --registry --name [--parent]                토픽 등록 [--commit]
  source    --layer --ref [--desc]                      소스 등록(READ ONLY) [--commit]
  publish   --topic --title --type --content --author [--parent]  지식 발행 [--commit]
  link      --type --source --target                    링크 [--commit]
  share     --entry --from --to                         공유 [--commit]
  consume   --entry --agent [--reused]                  소비 [--commit]
  feedback  --entry --agent --score                     평가 [--commit]
  reuse     --entry                                     재사용 점수 [--commit]
  snapshot  [--scope] / report [--scope]                스냅샷/리포트 [--commit]
  entries [--topic] / topics / verify / replay / summary

실제 실행·승인·배포·상위 수정 없음 — 지식 공유·기록만.
SHARING ≠ EXECUTION · TRANSFER ≠ DEPLOYMENT · REUSE ≠ APPROVAL.
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
    from jarvis.knowledge_sharing.engine import KnowledgeSharingEngine
    return KnowledgeSharingEngine()


def _cmd_registry(a) -> int:
    r = _eng().register_registry(a.name, a.mandate or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "registry": r.to_dict()})
    return 0


def _cmd_topic(a) -> int:
    t = _eng().register_topic(a.registry, a.name, a.desc or "", a.parent or "", _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "topic": t.to_dict()})
    return 0


def _cmd_source(a) -> int:
    s = _eng().register_source(a.layer, a.ref, a.desc or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "source": s.to_dict()})
    return 0


def _cmd_publish(a) -> int:
    e = _eng().publish_knowledge(a.topic, a.title, a.type, a.content, a.author, a.source or "",
                                 a.parent or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "entry": e.to_dict()})
    return 0


def _cmd_link(a) -> int:
    l = _eng().link_knowledge(a.type, a.source, a.target, a.relation or "relates", _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "link": l.to_dict()})
    return 0


def _cmd_share(a) -> int:
    t = _eng().share_with_agent(a.entry, a.getattr_from, a.to, a.note or "", _now(),
                                commit=a.commit)
    _p({"committed": a.commit, "transfer": t.to_dict()})
    return 0


def _cmd_consume(a) -> int:
    c = _eng().record_consumption(a.entry, a.agent, a.reused, a.note or "", _now(),
                                  commit=a.commit)
    _p({"committed": a.commit, "consumer": c.to_dict()})
    return 0


def _cmd_feedback(a) -> int:
    r = _eng().record_feedback(a.entry, a.agent, a.score, a.comment or "", _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "rating": r.to_dict()})
    return 0


def _cmd_reuse(a) -> int:
    _p({"committed": a.commit, "reuse": _eng().calculate_reuse_score(a.entry, _now(),
                                                                     commit=a.commit)})
    return 0


def _cmd_snapshot(a) -> int:
    s = _eng().snapshot_knowledge(a.scope or "GLOBAL", _now(), commit=a.commit)
    _p({"committed": a.commit, "snapshot": s.to_dict()})
    return 0


def _cmd_report(a) -> int:
    r = _eng().generate_report(a.scope or "GLOBAL", _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "note": "is_binding=False"})
    return 0


def _cmd_entries(a) -> int:
    _p({"entries": _eng().list_entries(a.topic or "")})
    return 0


def _cmd_topics(a) -> int:
    _p({"topics": _eng().list_topics()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.knowledge_sharing.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.knowledge_sharing.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.knowledge_sharing")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rg = sub.add_parser("registry")
    rg.add_argument("--name", required=True)
    rg.add_argument("--mandate", default="")
    rg.add_argument("--commit", action="store_true")
    tp = sub.add_parser("topic")
    tp.add_argument("--registry", required=True)
    tp.add_argument("--name", required=True)
    tp.add_argument("--desc", default="")
    tp.add_argument("--parent", default="")
    tp.add_argument("--commit", action="store_true")
    so = sub.add_parser("source")
    so.add_argument("--layer", required=True)
    so.add_argument("--ref", required=True)
    so.add_argument("--desc", default="")
    so.add_argument("--commit", action="store_true")
    pu = sub.add_parser("publish")
    pu.add_argument("--topic", required=True)
    pu.add_argument("--title", required=True)
    pu.add_argument("--type", required=True)
    pu.add_argument("--content", required=True)
    pu.add_argument("--author", required=True)
    pu.add_argument("--source", default="")
    pu.add_argument("--parent", default="")
    pu.add_argument("--commit", action="store_true")
    ln = sub.add_parser("link")
    ln.add_argument("--type", required=True)
    ln.add_argument("--source", required=True)
    ln.add_argument("--target", required=True)
    ln.add_argument("--relation", default="relates")
    ln.add_argument("--commit", action="store_true")
    sh = sub.add_parser("share")
    sh.add_argument("--entry", required=True)
    sh.add_argument("--from", dest="getattr_from", required=True)
    sh.add_argument("--to", required=True)
    sh.add_argument("--note", default="")
    sh.add_argument("--commit", action="store_true")
    cs = sub.add_parser("consume")
    cs.add_argument("--entry", required=True)
    cs.add_argument("--agent", required=True)
    cs.add_argument("--reused", action="store_true")
    cs.add_argument("--note", default="")
    cs.add_argument("--commit", action="store_true")
    fb = sub.add_parser("feedback")
    fb.add_argument("--entry", required=True)
    fb.add_argument("--agent", required=True)
    fb.add_argument("--score", type=int, required=True)
    fb.add_argument("--comment", default="")
    fb.add_argument("--commit", action="store_true")
    ru = sub.add_parser("reuse")
    ru.add_argument("--entry", required=True)
    ru.add_argument("--commit", action="store_true")
    sn = sub.add_parser("snapshot")
    sn.add_argument("--scope", default="GLOBAL")
    sn.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="GLOBAL")
    rp.add_argument("--commit", action="store_true")
    en = sub.add_parser("entries")
    en.add_argument("--topic", default="")
    sub.add_parser("topics")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"registry": _cmd_registry, "topic": _cmd_topic, "source": _cmd_source,
            "publish": _cmd_publish, "link": _cmd_link, "share": _cmd_share, "consume": _cmd_consume,
            "feedback": _cmd_feedback, "reuse": _cmd_reuse, "snapshot": _cmd_snapshot,
            "report": _cmd_report, "entries": _cmd_entries, "topics": _cmd_topics,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
