"""`python -m jarvis.research_resource_manager <cmd>` — 연구 자원 관리 CLI. **자동 배분·프로비저닝 없음.**

  resource   --type --name [--capacity --unit]             자원 등록 [--commit]
  usage      --resource --amount [--purpose --unit]        사용 기록 [--commit]
  budget     --category --amount [--currency --period]     예산 기록 [--commit]
  allocation --resource --experiment --amount [--unit]     배분 기록(자동/프로비저닝 없음) [--commit]
  utilization --resource                                   사용률 관찰
  report [--scope] / verify / summary / replay

자동 배분·인프라 프로비저닝·실행·거래 없음. RECORD ≠ ALLOCATE · RECORD ≠ PROVISION.
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
    from jarvis.research_resource_manager.engine import ResearchResourceManagerEngine
    return ResearchResourceManagerEngine()


def _cmd_resource(a) -> int:
    _p({"committed": a.commit,
        "resource": _eng().register_resource(a.type, a.name, a.capacity, a.unit or "units", "",
                                            _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_usage(a) -> int:
    _p({"committed": a.commit,
        "usage": _eng().record_usage(a.resource, a.amount, a.unit or "units",
                                   a.purpose or "EXPERIMENT", "", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_budget(a) -> int:
    _p({"committed": a.commit,
        "budget": _eng().record_budget(a.category, a.amount, a.currency or "USD", a.period or "",
                                     _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_allocation(a) -> int:
    _p({"committed": a.commit,
        "allocation": _eng().record_allocation(a.resource, a.experiment, a.amount, a.unit or "units",
                                             _now(), commit=a.commit).to_dict(),
        "note": "is_provisioned=False · is_auto=False"})
    return 0


def _cmd_utilization(a) -> int:
    _p(_eng().compute_utilization(a.resource))
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_resource_manager.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_resource_manager.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_resource_manager")
    sub = ap.add_subparsers(dest="cmd", required=True)

    re = sub.add_parser("resource")
    re.add_argument("--type", required=True)
    re.add_argument("--name", required=True)
    re.add_argument("--capacity", type=float, default=0.0)
    re.add_argument("--unit", default="units")
    re.add_argument("--commit", action="store_true")

    us = sub.add_parser("usage")
    us.add_argument("--resource", required=True)
    us.add_argument("--amount", type=float, required=True)
    us.add_argument("--purpose", default="EXPERIMENT")
    us.add_argument("--unit", default="units")
    us.add_argument("--commit", action="store_true")

    bu = sub.add_parser("budget")
    bu.add_argument("--category", required=True)
    bu.add_argument("--amount", type=float, required=True)
    bu.add_argument("--currency", default="USD")
    bu.add_argument("--period", default="")
    bu.add_argument("--commit", action="store_true")

    al = sub.add_parser("allocation")
    al.add_argument("--resource", required=True)
    al.add_argument("--experiment", required=True)
    al.add_argument("--amount", type=float, required=True)
    al.add_argument("--unit", default="units")
    al.add_argument("--commit", action="store_true")

    ut = sub.add_parser("utilization")
    ut.add_argument("--resource", required=True)

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"resource": _cmd_resource, "usage": _cmd_usage, "budget": _cmd_budget,
            "allocation": _cmd_allocation, "utilization": _cmd_utilization, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
