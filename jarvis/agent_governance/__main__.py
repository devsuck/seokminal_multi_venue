"""`python -m jarvis.agent_governance <cmd>` — 연구 에이전트 거버넌스 CLI. **관리·감사 전용.**

  agent      --agent-id --name --version --provider [--capabilities c1,c2] [--activate] [--commit]
  capability --agent-id --capability [--commit]
  request    --agent-id --objective [--sources s1,s2] [--commit]
  propose    --request-id --hypothesis [--methodology --expected --risk-notes] [--submit] [--commit]
  review     --proposal-id --reviewer --decision [--reason] [--commit]
  action     --agent-id --action-type [--target --result] [--commit]
  budget     --agent-id --period --max-experiments --max-queries [--commit]
  consume    --agent-id --period --kind [--commit]
  report / verify / summary / replay

실제 주문·전략배포·live trading·portfolio 변경·capital allocation 없음 — 기록·감사만.
Agent VALIDATED ≠ APPROVED FOR TRADING · Proposal ACCEPTED ≠ Execution permission.
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
    from jarvis.agent_governance.engine import AgentGovernanceEngine
    return AgentGovernanceEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_agent(a) -> int:
    eng = _eng()
    ag = eng.register_agent(a.agent_id, a.name, a.version, a.provider,
                            _split(a.capabilities), _now(), commit=a.commit)
    if a.activate:
        eng.activate_agent(a.agent_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "agent": ag.to_dict(),
        "note": "Agent VALIDATED ≠ APPROVED FOR TRADING"})
    return 0


def _cmd_capability(a) -> int:
    c = _eng().grant_capability(a.agent_id, a.capability, _now(), commit=a.commit)
    _p({"committed": a.commit, "capability": c.to_dict(), "note": "메타데이터 — 실제 권한 아님"})
    return 0


def _cmd_request(a) -> int:
    r = _eng().create_request(a.agent_id, a.objective, _split(a.sources), _now(), commit=a.commit)
    _p({"committed": a.commit, "request": r.to_dict()})
    return 0


def _cmd_propose(a) -> int:
    eng = _eng()
    p = eng.create_proposal(a.request_id, a.hypothesis, a.methodology or "", a.expected or "",
                            a.risk_notes or "", _now(), commit=a.commit)
    if a.submit:
        eng.submit_proposal(p.proposal_id, _now(), commit=a.commit)
    _p({"committed": a.commit, "proposal": p.to_dict(), "note": "ACCEPTED ≠ EXECUTION"})
    return 0


def _cmd_review(a) -> int:
    rv = _eng().record_review(a.proposal_id, a.reviewer, a.decision, a.reason or "", _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "review": rv.to_dict(), "note": "자동 승인 금지 — 사람 검토"})
    return 0


def _cmd_action(a) -> int:
    act = _eng().record_action(a.agent_id, a.action_type, a.target or "", a.result or "logged",
                               _now(), commit=a.commit)
    _p({"committed": a.commit, "action": act.to_dict(),
        "note": "금지 행동은 BLOCKED 기록만 — 실행 불가"})
    return 0


def _cmd_budget(a) -> int:
    b = _eng().set_budget(a.agent_id, a.period, a.max_experiments, a.max_queries, _now(),
                          commit=a.commit)
    _p({"committed": a.commit, "budget": b.to_dict(), "note": "연구 메타데이터 — 실제 실행 제한 아님"})
    return 0


def _cmd_consume(a) -> int:
    b = _eng().consume_budget(a.agent_id, a.period, a.kind, _now(), commit=a.commit)
    _p({"committed": a.commit, "usage": b.to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p(_eng().generate_report(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.agent_governance.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.agent_governance.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.agent_governance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ag = sub.add_parser("agent")
    for f in ("agent-id", "name", "version", "provider"):
        ag.add_argument(f"--{f}", required=True)
    ag.add_argument("--capabilities", default="")
    ag.add_argument("--activate", action="store_true")
    ag.add_argument("--commit", action="store_true")
    cp = sub.add_parser("capability")
    cp.add_argument("--agent-id", required=True)
    cp.add_argument("--capability", required=True)
    cp.add_argument("--commit", action="store_true")
    rq = sub.add_parser("request")
    rq.add_argument("--agent-id", required=True)
    rq.add_argument("--objective", required=True)
    rq.add_argument("--sources", default="")
    rq.add_argument("--commit", action="store_true")
    pr = sub.add_parser("propose")
    pr.add_argument("--request-id", required=True)
    pr.add_argument("--hypothesis", required=True)
    pr.add_argument("--methodology", default="")
    pr.add_argument("--expected", default="")
    pr.add_argument("--risk-notes", default="")
    pr.add_argument("--submit", action="store_true")
    pr.add_argument("--commit", action="store_true")
    rv = sub.add_parser("review")
    rv.add_argument("--proposal-id", required=True)
    rv.add_argument("--reviewer", required=True)
    rv.add_argument("--decision", required=True, choices=("APPROVE", "REJECT", "REQUEST_CHANGE"))
    rv.add_argument("--reason", default="")
    rv.add_argument("--commit", action="store_true")
    ac = sub.add_parser("action")
    ac.add_argument("--agent-id", required=True)
    ac.add_argument("--action-type", required=True)
    ac.add_argument("--target", default="")
    ac.add_argument("--result", default="logged")
    ac.add_argument("--commit", action="store_true")
    bg = sub.add_parser("budget")
    bg.add_argument("--agent-id", required=True)
    bg.add_argument("--period", required=True)
    bg.add_argument("--max-experiments", type=int, default=0)
    bg.add_argument("--max-queries", type=int, default=0)
    bg.add_argument("--commit", action="store_true")
    cs = sub.add_parser("consume")
    cs.add_argument("--agent-id", required=True)
    cs.add_argument("--period", required=True)
    cs.add_argument("--kind", required=True, choices=("experiment", "query"))
    cs.add_argument("--commit", action="store_true")
    sub.add_parser("report")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"agent": _cmd_agent, "capability": _cmd_capability, "request": _cmd_request,
            "propose": _cmd_propose, "review": _cmd_review, "action": _cmd_action,
            "budget": _cmd_budget, "consume": _cmd_consume, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_report, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
