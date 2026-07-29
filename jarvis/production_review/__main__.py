"""`python -m jarvis.production_review <cmd>` — 프로덕션 준비성 검토 CLI. **배포 없음, 평가만.**

  generate                production_review/ 8개 문서 생성(신규 파일)
  assess                  준비성 평가(재현성·복구성·관측성·유지보수성)
  list                    문서 목록
"""
from __future__ import annotations

import argparse
import json


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_generate(a) -> int:
    from jarvis.production_review.generator import write_docs
    written = write_docs()
    _p({"generated": [w.split("production_review/")[-1] for w in written], "count": len(written)})
    return 0


def _cmd_assess(a) -> int:
    from jarvis.production_review.assess import run_readiness_assessment
    res = run_readiness_assessment()
    _p(res)
    return 0 if res["ready"] else 1


def _cmd_list(a) -> int:
    from jarvis.production_review.models import PRODUCTION_DOCS
    _p({"docs": list(PRODUCTION_DOCS)})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.production_review")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate")
    sub.add_parser("assess")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    return {"generate": _cmd_generate, "assess": _cmd_assess, "list": _cmd_list}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
