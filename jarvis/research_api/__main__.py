"""`python -m jarvis.research_api <cmd>` — 대시보드·AI 에이전트용 조회 백엔드 CLI. **읽기 전용.**

  bootstrap                         기본 스키마·엔드포인트·뷰·쿼리 등록 [--commit]
  status                            get_system_status [--commit]
  timeline [--limit]                get_research_timeline [--commit]
  lineage  --strategy               get_strategy_lineage [--commit]
  alpha                             get_alpha_summary [--commit]
  risk                              get_risk_summary [--commit]
  agent                             get_agent_summary [--commit]
  governance                        get_governance_report [--commit]
  endpoints                         등록 엔드포인트 목록
  verify / replay / summary

실제 거래 실행·주문·배포 없음 — 조회·데이터 접근만. POST 실행 엔드포인트 없음.
READ ≠ WRITE · QUERY ≠ EXECUTE · API ≠ TRADE.
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
    from jarvis.research_api.engine import ResearchAPIEngine
    return ResearchAPIEngine()


def _cmd_bootstrap(a) -> int:
    _p({"committed": a.commit, "registered": _eng().bootstrap(_now(), commit=a.commit)})
    return 0


def _cmd_status(a) -> int:
    _p(_eng().get_system_status(_now(), commit=a.commit).to_dict())
    return 0


def _cmd_timeline(a) -> int:
    _p(_eng().get_research_timeline(a.limit or 0, _now(), commit=a.commit).to_dict())
    return 0


def _cmd_lineage(a) -> int:
    _p(_eng().get_strategy_lineage(a.strategy, _now(), commit=a.commit).to_dict())
    return 0


def _cmd_alpha(a) -> int:
    _p(_eng().get_alpha_summary(_now(), commit=a.commit).to_dict())
    return 0


def _cmd_risk(a) -> int:
    _p(_eng().get_risk_summary(_now(), commit=a.commit).to_dict())
    return 0


def _cmd_agent(a) -> int:
    _p(_eng().get_agent_summary(_now(), commit=a.commit).to_dict())
    return 0


def _cmd_governance(a) -> int:
    _p(_eng().get_governance_report(_now(), commit=a.commit).to_dict())
    return 0


def _cmd_endpoints(a) -> int:
    _p({"endpoints": _eng().list_endpoints()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_api.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_api.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_api")
    sub = ap.add_subparsers(dest="cmd", required=True)
    bs = sub.add_parser("bootstrap")
    bs.add_argument("--commit", action="store_true")
    for name in ("status", "alpha", "risk", "agent", "governance"):
        s = sub.add_parser(name)
        s.add_argument("--commit", action="store_true")
    tl = sub.add_parser("timeline")
    tl.add_argument("--limit", type=int, default=0)
    tl.add_argument("--commit", action="store_true")
    ln = sub.add_parser("lineage")
    ln.add_argument("--strategy", required=True)
    ln.add_argument("--commit", action="store_true")
    sub.add_parser("endpoints")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"bootstrap": _cmd_bootstrap, "status": _cmd_status, "timeline": _cmd_timeline,
            "lineage": _cmd_lineage, "alpha": _cmd_alpha, "risk": _cmd_risk, "agent": _cmd_agent,
            "governance": _cmd_governance, "endpoints": _cmd_endpoints, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
