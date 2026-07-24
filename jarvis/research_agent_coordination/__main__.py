"""`python -m jarvis.research_agent_coordination <cmd>` — 연구 에이전트 조정 CLI. **협업 조정 전용.**

  agent     --name --version [--capabilities --source]     에이전트 등록 [--commit]
  role      --name [--responsibility --actions]            역할 정의(금지 행동 불가) [--commit]
  team      --objective [--members]                        팀 생성 [--commit]
  session   --objective [--team]                           세션 생성(CREATED) [--commit]
  task      --session --agent --objective [--source --deps]  작업 위임(ASSIGNED) [--commit]
  message   --session --agent --content                    토론 메시지 [--commit]
  consensus --session [--positions --summary]              합의 기록(자동 결정 없음) [--commit]
  report [--scope] / verify / summary / replay

거래·주문·자본 배분·전략 배포·라이브 승인·권한 수정·자율 투자 결정 없음. CONSENSUS ≠ APPROVAL · COORDINATION ≠ EXECUTION.
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
    from jarvis.research_agent_coordination.engine import ResearchAgentCoordinator
    return ResearchAgentCoordinator()


def _split(s):
    return [x for x in (s or "").split("|") if x]


def _positions(s):
    out = {}
    for pair in _split(s):
        if ":" in pair:
            k, v = pair.split(":", 1)
            out[k] = v
    return out


def _cmd_agent(a) -> int:
    _p({"committed": a.commit,
        "agent": _eng().register_agent(a.name, a.version, _split(a.capabilities), a.source or "",
                                      _now(), commit=a.commit).to_dict(),
        "note": "identity immutable · permissions owned by P10.6"})
    return 0


def _cmd_role(a) -> int:
    _p({"committed": a.commit,
        "role": _eng().define_role(a.name, a.responsibility or "", _split(a.actions), _now(),
                                  commit=a.commit).to_dict(),
        "note": "no forbidden actions (role separation)"})
    return 0


def _cmd_team(a) -> int:
    _p({"committed": a.commit,
        "team": _eng().create_team(a.objective, _split(a.members), _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_session(a) -> int:
    _p({"committed": a.commit,
        "session": _eng().create_session(a.objective, a.team or "", _now(),
                                        commit=a.commit).to_dict()})
    return 0


def _cmd_task(a) -> int:
    _p({"committed": a.commit,
        "task": _eng().assign_task(a.session, a.agent, a.objective, a.source or "", _split(a.deps),
                                 _now(), commit=a.commit).to_dict(),
        "note": "owner + objective required (task isolation)"})
    return 0


def _cmd_message(a) -> int:
    _p({"committed": a.commit,
        "message": _eng().record_message(a.session, a.agent, a.content, [], _now(),
                                       commit=a.commit).to_dict()})
    return 0


def _cmd_consensus(a) -> int:
    _p({"committed": a.commit,
        "consensus": _eng().record_consensus(a.session, _positions(a.positions), a.summary or "",
                                            _now(), commit=a.commit).to_dict(),
        "note": "is_decision=False · CONSENSUS ≠ APPROVAL"})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_agent_coordination.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_agent_coordination.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_agent_coordination")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ag = sub.add_parser("agent")
    ag.add_argument("--name", required=True)
    ag.add_argument("--version", required=True)
    ag.add_argument("--capabilities", default="")
    ag.add_argument("--source", default="")
    ag.add_argument("--commit", action="store_true")

    ro = sub.add_parser("role")
    ro.add_argument("--name", required=True)
    ro.add_argument("--responsibility", default="")
    ro.add_argument("--actions", default="")
    ro.add_argument("--commit", action="store_true")

    tm = sub.add_parser("team")
    tm.add_argument("--objective", required=True)
    tm.add_argument("--members", default="")
    tm.add_argument("--commit", action="store_true")

    se = sub.add_parser("session")
    se.add_argument("--objective", required=True)
    se.add_argument("--team", default="")
    se.add_argument("--commit", action="store_true")

    tk = sub.add_parser("task")
    tk.add_argument("--session", required=True)
    tk.add_argument("--agent", required=True)
    tk.add_argument("--objective", required=True)
    tk.add_argument("--source", default="")
    tk.add_argument("--deps", default="")
    tk.add_argument("--commit", action="store_true")

    me = sub.add_parser("message")
    me.add_argument("--session", required=True)
    me.add_argument("--agent", required=True)
    me.add_argument("--content", required=True)
    me.add_argument("--commit", action="store_true")

    co = sub.add_parser("consensus")
    co.add_argument("--session", required=True)
    co.add_argument("--positions", default="")
    co.add_argument("--summary", default="")
    co.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"agent": _cmd_agent, "role": _cmd_role, "team": _cmd_team, "session": _cmd_session,
            "task": _cmd_task, "message": _cmd_message, "consensus": _cmd_consensus,
            "report": _cmd_report, "verify": _cmd_verify, "summary": _cmd_summary,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
