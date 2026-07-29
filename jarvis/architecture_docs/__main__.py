"""`python -m jarvis.architecture_docs <cmd>` — 아키텍처 문서 생성·검증 CLI. **문서화 전용.**

  generate                docs/architecture/ 9개 문서 생성(신규 파일)
  validate                아키텍처 일관성 검사
  list                    문서 카탈로그
"""
from __future__ import annotations

import argparse
import json


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_generate(a) -> int:
    from jarvis.architecture_docs.generator import write_docs
    written = write_docs()
    _p({"generated": [w.split("docs/architecture/")[-1] for w in written], "count": len(written)})
    return 0


def _cmd_validate(a) -> int:
    from jarvis.architecture_docs.validate import run_consistency_checks
    res = run_consistency_checks()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_list(a) -> int:
    from jarvis.architecture_docs.models import ARCHITECTURE_DOCS
    _p({"docs": list(ARCHITECTURE_DOCS)})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.architecture_docs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate")
    sub.add_parser("validate")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    return {"generate": _cmd_generate, "validate": _cmd_validate, "list": _cmd_list}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
