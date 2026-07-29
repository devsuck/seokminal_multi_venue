"""`python -m jarvis.release_candidate <cmd>` — Jarvis v1.0 RC CLI. **연구 보조만, 실행 없음.**

  generate                release/ 7개 산출물 생성(신규 파일)
  gate                    릴리스 게이트(무결성·보안·준비성·재현·의존성)
  status                  릴리스 상태 선언
  version                 버전
"""
from __future__ import annotations

import argparse
import json


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_generate(a) -> int:
    from jarvis.release_candidate.generator import write_artifacts
    written = write_artifacts()
    _p({"generated": [w.split("release/")[-1] for w in written], "count": len(written)})
    return 0


def _cmd_gate(a) -> int:
    from jarvis.release_candidate.gate import run_release_gate
    res = run_release_gate()
    _p(res)
    return 0 if res["approved"] else 1


def _cmd_status(a) -> int:
    from jarvis.release_candidate.models import PLATFORM_NAME, STATUS_STATEMENTS, VERSION
    _p({"platform": PLATFORM_NAME, "version": VERSION, "status": list(STATUS_STATEMENTS)})
    return 0


def _cmd_version(a) -> int:
    from jarvis.release_candidate.models import VERSION
    print(VERSION)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.release_candidate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate")
    sub.add_parser("gate")
    sub.add_parser("status")
    sub.add_parser("version")
    args = ap.parse_args(argv)
    disp = {"generate": _cmd_generate, "gate": _cmd_gate, "status": _cmd_status,
            "version": _cmd_version}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
