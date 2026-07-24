"""`python -m jarvis.documentation <cmd>` — 문서 검증·생성 CLI. **검증·생성 전용.**

  gen                    API 참조(documentation/api/reference.md) 자동 생성
  validate               전체 문서 검증(완전성·마크다운·링크·다이어그램·API 커버리지)
  cli                    CLI 보유 패키지 목록
  packages               공개 패키지 목록

거래·집행·배포 없음. 관찰·문서화 전용.
"""
from __future__ import annotations

import argparse
import json


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_gen(a) -> int:
    from jarvis.documentation.apidoc import write_reference
    path = write_reference()
    _p({"generated": path})
    return 0


def _cmd_validate(a) -> int:
    from jarvis.documentation.validate import validate_all
    res = validate_all()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_cli(a) -> int:
    from jarvis.documentation.apidoc import cli_inventory
    _p({"cli_packages": cli_inventory()})
    return 0


def _cmd_packages(a) -> int:
    from jarvis.documentation.manifest import discover_packages
    _p({"packages": discover_packages()})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.documentation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gen")
    sub.add_parser("validate")
    sub.add_parser("cli")
    sub.add_parser("packages")
    args = ap.parse_args(argv)
    return {"gen": _cmd_gen, "validate": _cmd_validate, "cli": _cmd_cli,
            "packages": _cmd_packages}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
