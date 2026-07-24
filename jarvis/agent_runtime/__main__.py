"""`python -m jarvis.agent_runtime <cmd>` — 연구 에이전트 런타임 CLI. **거래·배포·실행 없음.**

  agent    --name --role [--cap ...]                       에이전트 등록(CREATED) [--commit]
  state    --agent --to                                    상태 전이 [--commit]
  assign   --agent --title [--description]                 태스크 배정 [--commit]
  output   --agent --task --kind [--summary]               산출물 기록 [--commit]
  memref   --agent --layer --ref [--purpose]               메모리 참조(READ ONLY) [--commit]
  log      --agent --level --message                       활동 로그 [--commit]
  report [--scope] / verify / summary / replay

거래·배포·실행·자본 배분 없음. AGENT RUNTIME ≠ AUTONOMOUS TRADING · 산출물은 사람 검토용. 무제한 도구 접근 없음.
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
    from jarvis.agent_runtime.engine import AgentRuntimeEngine
    return AgentRuntimeEngine()


def _cmd_agent(a) -> int:
    _p({"committed": a.commit,
        "agent": _eng().register_agent(a.name, a.role, a.cap or [], _now(),
                                       commit=a.commit).to_dict()})
    return 0


def _cmd_state(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().track_state(a.agent, a.to, "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_assign(a) -> int:
    _p({"committed": a.commit,
        "assignment": _eng().assign_task(a.agent, a.title, a.description or "", _now(),
                                        commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_output(a) -> int:
    _p({"committed": a.commit,
        "output": _eng().record_output(a.agent, a.task, a.kind, {"k": a.summary}, a.summary or "",
                                       _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False · is_executed=False"})
    return 0


def _cmd_memref(a) -> int:
    _p({"committed": a.commit,
        "memref": _eng().reference_memory(a.agent, a.layer, a.ref, a.purpose or "", _now(),
                                         commit=a.commit).to_dict(),
        "note": "is_read_only=True"})
    return 0


def _cmd_log(a) -> int:
    _p({"committed": a.commit,
        "log": _eng().log_activity(a.agent, a.level, a.message, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_agent_report(a.scope or "SYSTEM", _now(),
                                               commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.agent_runtime.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.agent_runtime.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.agent_runtime")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ag = sub.add_parser("agent")
    ag.add_argument("--name", required=True)
    ag.add_argument("--role", required=True)
    ag.add_argument("--cap", action="append", default=[])
    ag.add_argument("--commit", action="store_true")

    st = sub.add_parser("state")
    st.add_argument("--agent", required=True)
    st.add_argument("--to", required=True)
    st.add_argument("--commit", action="store_true")

    asg = sub.add_parser("assign")
    asg.add_argument("--agent", required=True)
    asg.add_argument("--title", required=True)
    asg.add_argument("--description", default="")
    asg.add_argument("--commit", action="store_true")

    op = sub.add_parser("output")
    op.add_argument("--agent", required=True)
    op.add_argument("--task", required=True)
    op.add_argument("--kind", required=True)
    op.add_argument("--summary", default="")
    op.add_argument("--commit", action="store_true")

    mr = sub.add_parser("memref")
    mr.add_argument("--agent", required=True)
    mr.add_argument("--layer", required=True)
    mr.add_argument("--ref", required=True)
    mr.add_argument("--purpose", default="")
    mr.add_argument("--commit", action="store_true")

    lg = sub.add_parser("log")
    lg.add_argument("--agent", required=True)
    lg.add_argument("--level", required=True)
    lg.add_argument("--message", required=True)
    lg.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"agent": _cmd_agent, "state": _cmd_state, "assign": _cmd_assign, "output": _cmd_output,
            "memref": _cmd_memref, "log": _cmd_log, "report": _cmd_report, "verify": _cmd_verify,
            "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
