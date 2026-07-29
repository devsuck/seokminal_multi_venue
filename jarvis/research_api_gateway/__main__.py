"""`python -m jarvis.research_api_gateway <cmd>` — 연구 통합 읽기 전용 API 게이트웨이 CLI.

  service  --type --name [--description]                    읽기 전용 서비스 등록 [--commit]
  query    --type [--layer]                                 읽기 전용 질의 실행 [--commit]
  get      --service [--layer]                              즉시 조회(감사 없음)
  report [--scope] / verify / summary / replay

거래·배포·실행·승인·배분 노출 없음. READ ONLY · GATEWAY ≠ EXECUTION · QUERY ≠ MUTATION.
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
    from jarvis.research_api_gateway.engine import ResearchApiGatewayEngine
    return ResearchApiGatewayEngine()


def _cmd_service(a) -> int:
    _p({"committed": a.commit,
        "service": _eng().register_service(a.type, a.name, a.description or "", _now(),
                                         commit=a.commit).to_dict(),
        "note": "is_readonly=True"})
    return 0


def _cmd_query(a) -> int:
    _p({"committed": a.commit,
        "response": _eng().query(a.type, a.layer, {}, _now(), commit=a.commit).to_dict(),
        "note": "READ ONLY · QUERY ≠ MUTATION"})
    return 0


def _cmd_get(a) -> int:
    e = _eng()
    disp = {"KNOWLEDGE_QUERY": e.get_knowledge, "RESEARCH_SUMMARY": lambda l=None: e.get_summary(),
            "HISTORY": e.get_history, "METRICS": e.get_metrics, "REPORTS": e.get_reports,
            "LINEAGE": e.get_lineage}
    fn = disp.get(a.service)
    if not fn:
        _p({"error": f"unknown service {a.service}"})
        return 1
    _p(fn(a.layer) if a.layer else fn())
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_api_gateway.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.research_api_gateway.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_api_gateway")
    sub = ap.add_subparsers(dest="cmd", required=True)

    se = sub.add_parser("service")
    se.add_argument("--type", required=True)
    se.add_argument("--name", required=True)
    se.add_argument("--description", default="")
    se.add_argument("--commit", action="store_true")

    qu = sub.add_parser("query")
    qu.add_argument("--type", required=True)
    qu.add_argument("--layer", default="")
    qu.add_argument("--commit", action="store_true")

    ge = sub.add_parser("get")
    ge.add_argument("--service", required=True)
    ge.add_argument("--layer", default="")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"service": _cmd_service, "query": _cmd_query, "get": _cmd_get, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
