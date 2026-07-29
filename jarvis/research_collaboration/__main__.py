"""`python -m jarvis.research_collaboration <cmd>` — 다중 에이전트 연구 협업 CLI. **협업·조정·기록 전용.**

  collab   --name [--objective]                     협업 생성(CREATED) [--commit]
  invite   --collab --agent [--role --spec]          참여자 초대(INVITED) [--commit]
  message  --collab --author --type [--content]      메시지 기록(불변) [--commit]
  proposal --collab --author --title                 제안 생성(DRAFT) [--commit]
  review   --collab --reviewer --target --category --score  동료검토 기록 [--commit]
  consensus --collab --topic                         합의 시작(OPEN) [--commit]
  conflict --collab --type [--desc]                  갈등 시작(OPEN) [--commit]
  hreview  --collab --subject                        사람검토 요청(REQUESTED) [--commit]
  report --collab / collaborations / verify / replay / summary

거래·전략 배포·권한 부여·자동 실행·자동 승인 없음. COLLABORATE ≠ EXECUTE · CONSENSUS ≠ APPROVAL.
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
    from jarvis.research_collaboration.engine import ResearchCollaborationEngine
    return ResearchCollaborationEngine()


def _cmd_collab(a) -> int:
    _p({"committed": a.commit,
        "collaboration": _eng().create_collaboration(a.name, a.objective or "", _now(),
                                                     commit=a.commit).to_dict()})
    return 0


def _cmd_invite(a) -> int:
    _p({"committed": a.commit,
        "participant": _eng().invite_participant(a.collab, a.agent, a.role or "researcher",
                                                a.spec or "", "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_message(a) -> int:
    _p({"committed": a.commit,
        "message": _eng().post_message(a.collab, a.author, a.type, a.content or "", [], {}, _now(),
                                      commit=a.commit).to_dict()})
    return 0


def _cmd_proposal(a) -> int:
    _p({"committed": a.commit,
        "proposal": _eng().create_proposal(a.collab, a.author, a.title, _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_review(a) -> int:
    _p({"committed": a.commit,
        "review": _eng().add_peer_review(a.collab, a.reviewer, a.target, a.category, a.score, "", [],
                                        _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_consensus(a) -> int:
    _p({"committed": a.commit,
        "consensus": _eng().open_consensus(a.collab, a.topic, _now(), commit=a.commit).to_dict(),
        "note": "CONSENSUS ≠ APPROVAL"})
    return 0


def _cmd_conflict(a) -> int:
    _p({"committed": a.commit,
        "conflict": _eng().open_conflict(a.collab, a.type, a.desc or "", _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_hreview(a) -> int:
    _p({"committed": a.commit,
        "human_review": _eng().request_human_review(a.collab, a.subject, _now(),
                                                   commit=a.commit).to_dict(),
        "note": "reviewer identity required · no auto acceptance"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.collab, "COLLABORATION", _now(),
                                        commit=a.commit).to_dict(), "note": "is_binding=False"})
    return 0


def _cmd_collaborations(a) -> int:
    eng = _eng()
    _p({"collaborations": [{"collaboration_id": c, "state": eng.collaboration_state(c)}
                           for c in eng.list_collaborations()]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_collaboration.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_collaboration.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_collaboration")
    sub = ap.add_subparsers(dest="cmd", required=True)

    cb = sub.add_parser("collab")
    cb.add_argument("--name", required=True)
    cb.add_argument("--objective", default="")
    cb.add_argument("--commit", action="store_true")

    iv = sub.add_parser("invite")
    iv.add_argument("--collab", required=True)
    iv.add_argument("--agent", required=True)
    iv.add_argument("--role", default="researcher")
    iv.add_argument("--spec", default="")
    iv.add_argument("--commit", action="store_true")

    ms = sub.add_parser("message")
    ms.add_argument("--collab", required=True)
    ms.add_argument("--author", required=True)
    ms.add_argument("--type", required=True)
    ms.add_argument("--content", default="")
    ms.add_argument("--commit", action="store_true")

    pp = sub.add_parser("proposal")
    pp.add_argument("--collab", required=True)
    pp.add_argument("--author", required=True)
    pp.add_argument("--title", required=True)
    pp.add_argument("--commit", action="store_true")

    rv = sub.add_parser("review")
    rv.add_argument("--collab", required=True)
    rv.add_argument("--reviewer", required=True)
    rv.add_argument("--target", required=True)
    rv.add_argument("--category", required=True)
    rv.add_argument("--score", type=float, required=True)
    rv.add_argument("--commit", action="store_true")

    cs = sub.add_parser("consensus")
    cs.add_argument("--collab", required=True)
    cs.add_argument("--topic", required=True)
    cs.add_argument("--commit", action="store_true")

    cf = sub.add_parser("conflict")
    cf.add_argument("--collab", required=True)
    cf.add_argument("--type", required=True)
    cf.add_argument("--desc", default="")
    cf.add_argument("--commit", action="store_true")

    hr = sub.add_parser("hreview")
    hr.add_argument("--collab", required=True)
    hr.add_argument("--subject", required=True)
    hr.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--collab", required=True)
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("collaborations")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"collab": _cmd_collab, "invite": _cmd_invite, "message": _cmd_message,
            "proposal": _cmd_proposal, "review": _cmd_review, "consensus": _cmd_consensus,
            "conflict": _cmd_conflict, "hreview": _cmd_hreview, "report": _cmd_report,
            "collaborations": _cmd_collaborations, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
