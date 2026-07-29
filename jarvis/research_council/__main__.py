"""`python -m jarvis.research_council <cmd>` — 다중 에이전트 연구 협의체 CLI. **협의·기록 전용.**

  council   --name [--mandate]                  협의체 등록 [--commit]
  session   --council --topic [--objective]     세션 생성(CREATED) [--commit]
  advance   --session --to ACTIVE|DISCUSSING|VOTING|CONSENSUS|CLOSED  전이 [--commit]
  invite    --session --agent --role            에이전트 초대 [--commit]
  argue     --session --agent --claim [--stance]  논증 [--commit]
  counter   --session --agent --parent --claim  반대 논증 [--commit]
  vote      --session --topic --agent --choice  투표 [--commit]
  consensus --session --topic                   합의 계산 [--commit]
  minority  --session --topic                   소수의견 보존 [--commit]
  summary-of --session --topic [--rec]          결정 요약 [--commit]
  report    --council                           협의체 리포트 [--commit]
  verify / replay / summary

실제 실행·승인·배포·거래·할당 없음 — 협의·권고만. 합의 ≠ 승인.
COUNCIL ≠ EXECUTION · CONSENSUS ≠ APPROVAL · RECOMMENDATION ≠ DEPLOYMENT.
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
    from jarvis.research_council.engine import ResearchCouncilEngine
    return ResearchCouncilEngine()


def _cmd_council(a) -> int:
    c = _eng().register_council(a.name, a.mandate or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "council": c.to_dict()})
    return 0


def _cmd_session(a) -> int:
    s = _eng().create_session(a.council, a.topic, a.objective or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "session": s.to_dict()})
    return 0


def _cmd_advance(a) -> int:
    e = _eng()
    fn = {"ACTIVE": e.activate_session, "DISCUSSING": e.start_discussion, "VOTING": e.open_voting,
          "CONSENSUS": e.reach_consensus, "CLOSED": e.close_session}[a.to]
    _p({"committed": a.commit, "session": fn(a.session, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_invite(a) -> int:
    p = _eng().invite_agent(a.session, a.agent, a.role, _now(), commit=a.commit)
    _p({"committed": a.commit, "participant": p.to_dict()})
    return 0


def _cmd_argue(a) -> int:
    r = _eng().submit_argument(a.session, a.agent, a.claim, a.stance or "FOR", _now(),
                               commit=a.commit)
    _p({"committed": a.commit, "argument": r.to_dict()})
    return 0


def _cmd_counter(a) -> int:
    r = _eng().submit_counter_argument(a.session, a.agent, a.parent, a.claim, _now(),
                                       commit=a.commit)
    _p({"committed": a.commit, "argument": r.to_dict()})
    return 0


def _cmd_vote(a) -> int:
    v = _eng().record_vote(a.session, a.topic, a.agent, a.choice, a.rationale or "", _now(),
                           commit=a.commit)
    _p({"committed": a.commit, "vote": v.to_dict()})
    return 0


def _cmd_consensus(a) -> int:
    c = _eng().calculate_consensus(a.session, a.topic, _now(), commit=a.commit)
    _p({"committed": a.commit, "consensus": c.to_dict(), "note": "CONSENSUS ≠ APPROVAL"})
    return 0


def _cmd_minority(a) -> int:
    ms = _eng().preserve_minority(a.session, a.topic, _now(), commit=a.commit)
    _p({"committed": a.commit, "minority": [m.to_dict() for m in ms]})
    return 0


def _cmd_summary_of(a) -> int:
    s = _eng().generate_summary(a.session, a.topic, a.rec or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "summary": s.to_dict(), "note": "is_decision=False"})
    return 0


def _cmd_report(a) -> int:
    r = _eng().generate_report(a.council, "COUNCIL", _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_council.verify import verify_chain
    res = verify_chain(check_minority=True)
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_council.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_council")
    sub = ap.add_subparsers(dest="cmd", required=True)
    co = sub.add_parser("council")
    co.add_argument("--name", required=True)
    co.add_argument("--mandate", default="")
    co.add_argument("--commit", action="store_true")
    se = sub.add_parser("session")
    se.add_argument("--council", required=True)
    se.add_argument("--topic", required=True)
    se.add_argument("--objective", default="")
    se.add_argument("--commit", action="store_true")
    ad = sub.add_parser("advance")
    ad.add_argument("--session", required=True)
    ad.add_argument("--to", required=True,
                    choices=["ACTIVE", "DISCUSSING", "VOTING", "CONSENSUS", "CLOSED"])
    ad.add_argument("--commit", action="store_true")
    iv = sub.add_parser("invite")
    iv.add_argument("--session", required=True)
    iv.add_argument("--agent", required=True)
    iv.add_argument("--role", required=True)
    iv.add_argument("--commit", action="store_true")
    ar = sub.add_parser("argue")
    ar.add_argument("--session", required=True)
    ar.add_argument("--agent", required=True)
    ar.add_argument("--claim", required=True)
    ar.add_argument("--stance", default="FOR")
    ar.add_argument("--commit", action="store_true")
    cn = sub.add_parser("counter")
    cn.add_argument("--session", required=True)
    cn.add_argument("--agent", required=True)
    cn.add_argument("--parent", required=True)
    cn.add_argument("--claim", required=True)
    cn.add_argument("--commit", action="store_true")
    vo = sub.add_parser("vote")
    vo.add_argument("--session", required=True)
    vo.add_argument("--topic", required=True)
    vo.add_argument("--agent", required=True)
    vo.add_argument("--choice", required=True, choices=["FOR", "AGAINST", "ABSTAIN"])
    vo.add_argument("--rationale", default="")
    vo.add_argument("--commit", action="store_true")
    cs = sub.add_parser("consensus")
    cs.add_argument("--session", required=True)
    cs.add_argument("--topic", required=True)
    cs.add_argument("--commit", action="store_true")
    mi = sub.add_parser("minority")
    mi.add_argument("--session", required=True)
    mi.add_argument("--topic", required=True)
    mi.add_argument("--commit", action="store_true")
    su = sub.add_parser("summary-of")
    su.add_argument("--session", required=True)
    su.add_argument("--topic", required=True)
    su.add_argument("--rec", default="")
    su.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--council", required=True)
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"council": _cmd_council, "session": _cmd_session, "advance": _cmd_advance,
            "invite": _cmd_invite, "argue": _cmd_argue, "counter": _cmd_counter, "vote": _cmd_vote,
            "consensus": _cmd_consensus, "minority": _cmd_minority, "summary-of": _cmd_summary_of,
            "report": _cmd_report, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
