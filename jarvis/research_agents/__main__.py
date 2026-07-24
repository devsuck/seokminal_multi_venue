"""`python -m jarvis.research_agents <cmd>` — 연구 보조 AI 에이전트 CLI. **연구 보조 전용.**

  register --name --type [--desc]        에이전트 등록 [--commit]
  profile  --agent --caps READ,ANALYZE   프로파일(역량) 등록 [--commit]
  task     --agent --action --target [--desc]  태스크 생성 [--commit]
  advance  --task --to ASSIGNED|...       태스크 전이 [--commit]
  message  --from --to --subject --content 메시지 [--commit]
  report   --agent --task --scope [--summary] 리포트 제출 [--commit]
  guard    --agent --action               행위 권한 검사(금지 행위 차단)
  agents [--type] / activity --agent / verify / replay / summary

실제 거래·실행·배포·할당 없음 — 읽기·분석·리포트만. 금지 행위(TRADE/EXECUTE/DEPLOY/ALLOCATE)는 차단·감사.
ASSIST ≠ EXECUTE · ANALYZE ≠ TRADE · REPORT ≠ DEPLOY.
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
    from jarvis.research_agents.engine import ResearchAgentEngine
    return ResearchAgentEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_register(a) -> int:
    ag = _eng().register_agent(a.name, a.type, a.desc or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "agent": ag.to_dict()})
    return 0


def _cmd_profile(a) -> int:
    p = _eng().create_profile(a.agent, _split(a.caps), a.desc or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "profile": p.to_dict()})
    return 0


def _cmd_task(a) -> int:
    t = _eng().create_task(a.agent, a.action, a.target, a.desc or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "task": t.to_dict()})
    return 0


def _cmd_advance(a) -> int:
    e = _eng()
    fn = {"ASSIGNED": e.assign_task, "IN_PROGRESS": e.start_task, "COMPLETED": e.complete_task,
          "FAILED": e.fail_task, "CANCELLED": e.cancel_task}[a.to]
    _p({"committed": a.commit, "task": fn(a.task, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_message(a) -> int:
    m = _eng().send_message(a.getattr_from, a.to, a.subject, a.content, _now(), commit=a.commit)
    _p({"committed": a.commit, "message": m.to_dict()})
    return 0


def _cmd_report(a) -> int:
    r = _eng().submit_report(a.agent, a.task, a.scope, _split(a.findings), a.summary or "",
                             _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "note": "REPORT ≠ DEPLOY"})
    return 0


def _cmd_guard(a) -> int:
    from jarvis.research_agents.models import ForbiddenAgentAction, CapabilityDenied, InvalidCapability
    try:
        _eng().guard_action(a.agent, a.action, _now(), commit=a.commit)
        _p({"allowed": True, "action": a.action})
        return 0
    except ForbiddenAgentAction as ex:
        _p({"allowed": False, "blocked": True, "reason": str(ex)})
        return 1
    except (CapabilityDenied, InvalidCapability) as ex:
        _p({"allowed": False, "reason": str(ex)})
        return 1


def _cmd_agents(a) -> int:
    _p({"agents": _eng().list_agents(a.type or "")})
    return 0


def _cmd_activity(a) -> int:
    _p({"activity": _eng().agent_activity(a.agent)})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_agents.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_agents.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_agents")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rg = sub.add_parser("register")
    rg.add_argument("--name", required=True)
    rg.add_argument("--type", required=True)
    rg.add_argument("--desc", default="")
    rg.add_argument("--commit", action="store_true")
    pf = sub.add_parser("profile")
    pf.add_argument("--agent", required=True)
    pf.add_argument("--caps", required=True)
    pf.add_argument("--desc", default="")
    pf.add_argument("--commit", action="store_true")
    tk = sub.add_parser("task")
    tk.add_argument("--agent", required=True)
    tk.add_argument("--action", required=True)
    tk.add_argument("--target", required=True)
    tk.add_argument("--desc", default="")
    tk.add_argument("--commit", action="store_true")
    ad = sub.add_parser("advance")
    ad.add_argument("--task", required=True)
    ad.add_argument("--to", required=True,
                    choices=["ASSIGNED", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED"])
    ad.add_argument("--commit", action="store_true")
    ms = sub.add_parser("message")
    ms.add_argument("--from", dest="getattr_from", required=True)
    ms.add_argument("--to", required=True)
    ms.add_argument("--subject", default="")
    ms.add_argument("--content", default="")
    ms.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--agent", required=True)
    rp.add_argument("--task", default="")
    rp.add_argument("--scope", default="GLOBAL")
    rp.add_argument("--findings", default="")
    rp.add_argument("--summary", default="")
    rp.add_argument("--commit", action="store_true")
    gd = sub.add_parser("guard")
    gd.add_argument("--agent", required=True)
    gd.add_argument("--action", required=True)
    gd.add_argument("--commit", action="store_true")
    ag = sub.add_parser("agents")
    ag.add_argument("--type", default="")
    ac = sub.add_parser("activity")
    ac.add_argument("--agent", required=True)
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"register": _cmd_register, "profile": _cmd_profile, "task": _cmd_task,
            "advance": _cmd_advance, "message": _cmd_message, "report": _cmd_report,
            "guard": _cmd_guard, "agents": _cmd_agents, "activity": _cmd_activity,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
