"""`python -m jarvis.governance_memory <cmd>` — 거버넌스 지식 메모리 CLI. **저장·조회 전용.**

  entry      --category --source-reference [--content --metadata-json --lesson-ref] [--commit]
  experience --event-reference [--outcome --impact --source-layer] [--commit]
  lesson     --observation --conclusion [--evidence e1,e2 --experience-ref] [--commit]
  link       --from-ref --link-type --to-ref [--commit]
  search     --ref
  snapshot   --name [--epoch --entries e1,e2 --summary-json] [--commit]
  report     [--metrics-json] [--commit]
  verify / replay / summary

실제 의사결정 실행·정책 변경·config 수정·strategy 승인·model 배포 없음 — 지식 저장·조회만.
MEMORY ≠ AUTHORITY · SIMILARITY ≠ DECISION · HISTORICAL PATTERN ≠ FUTURE ACTION · KNOWLEDGE ≠ PERMISSION.
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
    from jarvis.governance_memory.engine import GovernanceMemoryEngine
    return GovernanceMemoryEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_entry(a) -> int:
    meta = json.loads(a.metadata_json) if a.metadata_json else {}
    e = _eng().create_entry(a.category, a.source_reference, a.content or None, meta,
                            a.lesson_ref or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "entry": e.to_dict(), "note": "지식 저장 — 불변"})
    return 0


def _cmd_experience(a) -> int:
    x = _eng().record_experience(a.event_reference, a.outcome or "INCONCLUSIVE",
                                 a.impact or "MEDIUM", "", a.source_layer or "", _now(),
                                 commit=a.commit)
    _p({"committed": a.commit, "experience": x.to_dict(), "note": "경험 기록 — 불변"})
    return 0


def _cmd_lesson(a) -> int:
    l = _eng().store_lesson(a.observation, a.conclusion, _split(a.evidence), a.experience_ref or "",
                            _now(), commit=a.commit)
    _p({"committed": a.commit, "lesson": l.to_dict(), "note": "교훈 저장 — 불변"})
    return 0


def _cmd_link(a) -> int:
    eng = _eng()
    l = eng.link_memory(a.from_ref, a.link_type, a.to_ref, _now(), commit=a.commit)
    _p({"committed": a.commit, "link": l.to_dict(), "cycle": eng.link_cycle()})
    return 0


def _cmd_search(a) -> int:
    _p(_eng().search(a.ref))
    return 0


def _cmd_snapshot(a) -> int:
    summary = json.loads(a.summary_json) if a.summary_json else {}
    s = _eng().create_snapshot(a.name, a.epoch or "", _split(a.entries), summary, _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "snapshot": s.to_dict(), "note": "결정적 스냅샷"})
    return 0


def _cmd_report(a) -> int:
    metrics = json.loads(a.metrics_json) if a.metrics_json else {}
    r = _eng().generate_report("GLOBAL", metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.governance_memory.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.governance_memory.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.governance_memory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    en = sub.add_parser("entry")
    en.add_argument("--category", required=True)
    en.add_argument("--source-reference", required=True)
    en.add_argument("--content", default="")
    en.add_argument("--metadata-json", default="")
    en.add_argument("--lesson-ref", default="")
    en.add_argument("--commit", action="store_true")
    ex = sub.add_parser("experience")
    ex.add_argument("--event-reference", required=True)
    ex.add_argument("--outcome", default="INCONCLUSIVE")
    ex.add_argument("--impact", default="MEDIUM")
    ex.add_argument("--source-layer", default="")
    ex.add_argument("--commit", action="store_true")
    le = sub.add_parser("lesson")
    le.add_argument("--observation", required=True)
    le.add_argument("--conclusion", required=True)
    le.add_argument("--evidence", default="")
    le.add_argument("--experience-ref", default="")
    le.add_argument("--commit", action="store_true")
    li = sub.add_parser("link")
    li.add_argument("--from-ref", required=True)
    li.add_argument("--link-type", required=True)
    li.add_argument("--to-ref", required=True)
    li.add_argument("--commit", action="store_true")
    se = sub.add_parser("search")
    se.add_argument("--ref", required=True)
    sn = sub.add_parser("snapshot")
    sn.add_argument("--name", required=True)
    sn.add_argument("--epoch", default="")
    sn.add_argument("--entries", default="")
    sn.add_argument("--summary-json", default="")
    sn.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--metrics-json", default="")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"entry": _cmd_entry, "experience": _cmd_experience, "lesson": _cmd_lesson,
            "link": _cmd_link, "search": _cmd_search, "snapshot": _cmd_snapshot,
            "report": _cmd_report, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
