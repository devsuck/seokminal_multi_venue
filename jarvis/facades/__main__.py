"""`python -m jarvis.facades <cmd>` — 통합 파사드 CLI. **읽기전용, 무손실.**

  list                     파사드 목록
  members --name NAME      계열 멤버(존재 검증)
  resolve --module MOD     모듈이 속한 파사드
  summary                  전체 축소 효과 요약

하부 모듈 무변경. 거래·집행 없음.
"""
from __future__ import annotations

import argparse
import json


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _reg():
    from jarvis.facades.engine import FacadeRegistry
    return FacadeRegistry()


def _cmd_list(a) -> int:
    _p([f.to_dict() for f in _reg().all_facades()])
    return 0


def _cmd_members(a) -> int:
    _p(_reg().facade(a.name).to_dict())
    return 0


def _cmd_resolve(a) -> int:
    _p({"module": a.module, "facade": _reg().resolve(a.module)})
    return 0


def _cmd_summary(a) -> int:
    _p(_reg().summary())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.facades")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    me = sub.add_parser("members")
    me.add_argument("--name", required=True)
    rs = sub.add_parser("resolve")
    rs.add_argument("--module", required=True)
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"list": _cmd_list, "members": _cmd_members, "resolve": _cmd_resolve,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
