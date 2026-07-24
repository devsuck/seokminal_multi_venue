"""`python -m jarvis.research_organization <cmd>` — 자율 연구 조직 CLI. **조직 전용.**

  org        --name [--mandate]                          조직 생성(CREATED) [--commit]
  unit       --org --type --name [--desc]                연구 유닛(→CONFIGURED) [--commit]
  team       --unit --name [--desc]                      연구 팀 [--commit]
  role       --unit --agent --role [--team]              역할 배정 [--commit]
  activate   --org                                       CONFIGURED→ACTIVE [--commit]
  responsibility --org --owner --scope [--output --evidence --inputs]  책임 정의 [--commit]
  workflow   --org --name --owner-unit [--inputs --depends]  워크플로 소유 [--commit]
  policy     --org --name [--ptype --rule]               조정 정책(→COORDINATING) [--commit]
  evaluate   --org                                       건강 지표(분석 전용)
  snapshot   --org [--scope] / report --org [--scope] / units --org / verify / replay / summary

실제 실행·배포·승인·자본 배분·모델/전략 수정·권한 변경·자율 인가 없음 — 조직 조정·기록·분석만.
ORGANIZATION ≠ EXECUTION · ROLE ≠ AUTHORIZATION · METRIC ≠ ACTION.
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
    from jarvis.research_organization.engine import ResearchOrganizationEngine
    return ResearchOrganizationEngine()


def _cmd_org(a) -> int:
    _p({"committed": a.commit,
        "org": _eng().register_organization(a.name, a.mandate or "", _now(),
                                             commit=a.commit).to_dict()})
    return 0


def _cmd_unit(a) -> int:
    _p({"committed": a.commit,
        "unit": _eng().create_research_unit(a.org, a.type, a.name, a.desc or "", _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_team(a) -> int:
    _p({"committed": a.commit,
        "team": _eng().create_research_team(a.unit, a.name, a.desc or "", _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_role(a) -> int:
    _p({"committed": a.commit,
        "role": _eng().assign_agent_role(a.unit, a.agent, a.role, a.team or "", _now(),
                                         commit=a.commit).to_dict(),
        "note": "ROLE ≠ AUTHORIZATION"})
    return 0


def _cmd_activate(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().activate_organization(a.org, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_responsibility(a) -> int:
    inputs = a.inputs.split(",") if a.inputs else []
    _p({"committed": a.commit,
        "responsibility": _eng().define_responsibility(a.org, a.owner, a.scope, inputs,
                                                       a.output or "", a.evidence or "",
                                                       now=_now(), commit=a.commit).to_dict()})
    return 0


def _cmd_workflow(a) -> int:
    inputs = a.inputs.split(",") if a.inputs else []
    deps = a.depends.split(",") if a.depends else []
    _p({"committed": a.commit,
        "workflow": _eng().map_workflow_owner(a.org, a.name, a.owner_unit, inputs, deps, _now(),
                                             commit=a.commit).to_dict()})
    return 0


def _cmd_policy(a) -> int:
    _p({"committed": a.commit,
        "policy": _eng().create_coordination_policy(a.org, a.name, a.ptype or "", a.rule or "",
                                                   _now(), commit=a.commit).to_dict(),
        "note": "policy definition only, NOT execution"})
    return 0


def _cmd_evaluate(a) -> int:
    _p(_eng().evaluate_organization_state(a.org))
    return 0


def _cmd_snapshot(a) -> int:
    _p({"committed": a.commit,
        "snapshot": _eng().snapshot_organization(a.org, a.scope or "ALL", _now(),
                                                commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.org, a.scope or "ALL", _now(),
                                         commit=a.commit).to_dict(),
        "note": "is_binding=False · health metrics are analytical only"})
    return 0


def _cmd_units(a) -> int:
    _p({"units": _eng().list_units(a.org or "")})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_organization.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_organization.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_organization")
    sub = ap.add_subparsers(dest="cmd", required=True)

    og = sub.add_parser("org")
    og.add_argument("--name", required=True)
    og.add_argument("--mandate", default="")
    og.add_argument("--commit", action="store_true")

    un = sub.add_parser("unit")
    un.add_argument("--org", required=True)
    un.add_argument("--type", required=True)
    un.add_argument("--name", required=True)
    un.add_argument("--desc", default="")
    un.add_argument("--commit", action="store_true")

    tm = sub.add_parser("team")
    tm.add_argument("--unit", required=True)
    tm.add_argument("--name", required=True)
    tm.add_argument("--desc", default="")
    tm.add_argument("--commit", action="store_true")

    ro = sub.add_parser("role")
    ro.add_argument("--unit", required=True)
    ro.add_argument("--agent", required=True)
    ro.add_argument("--role", required=True,
                    choices=["RESEARCHER", "ANALYST", "REVIEWER", "COORDINATOR",
                             "KNOWLEDGE_MANAGER", "QUALITY_AUDITOR"])
    ro.add_argument("--team", default="")
    ro.add_argument("--commit", action="store_true")

    ac = sub.add_parser("activate")
    ac.add_argument("--org", required=True)
    ac.add_argument("--commit", action="store_true")

    rs = sub.add_parser("responsibility")
    rs.add_argument("--org", required=True)
    rs.add_argument("--owner", required=True)
    rs.add_argument("--scope", required=True)
    rs.add_argument("--output", default="")
    rs.add_argument("--evidence", default="")
    rs.add_argument("--inputs", default="")
    rs.add_argument("--commit", action="store_true")

    wf = sub.add_parser("workflow")
    wf.add_argument("--org", required=True)
    wf.add_argument("--name", required=True)
    wf.add_argument("--owner-unit", dest="owner_unit", required=True)
    wf.add_argument("--inputs", default="")
    wf.add_argument("--depends", default="")
    wf.add_argument("--commit", action="store_true")

    po = sub.add_parser("policy")
    po.add_argument("--org", required=True)
    po.add_argument("--name", required=True)
    po.add_argument("--ptype", default="")
    po.add_argument("--rule", default="")
    po.add_argument("--commit", action="store_true")

    ev = sub.add_parser("evaluate")
    ev.add_argument("--org", required=True)

    sn = sub.add_parser("snapshot")
    sn.add_argument("--org", required=True)
    sn.add_argument("--scope", default="ALL")
    sn.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--org", required=True)
    rp.add_argument("--scope", default="ALL")
    rp.add_argument("--commit", action="store_true")

    us = sub.add_parser("units")
    us.add_argument("--org", default="")

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"org": _cmd_org, "unit": _cmd_unit, "team": _cmd_team, "role": _cmd_role,
            "activate": _cmd_activate, "responsibility": _cmd_responsibility,
            "workflow": _cmd_workflow, "policy": _cmd_policy, "evaluate": _cmd_evaluate,
            "snapshot": _cmd_snapshot, "report": _cmd_report, "units": _cmd_units,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
