"""`python -m jarvis.system_integration <cmd>` — 시스템 통합·최종 검증 CLI. **통합·검증 전용.**

  validate                                                  전체 계층(P21~P34) 정적 검증 [--commit]
  architecture                                             아키텍처 요약
  dependencies                                             의존성 그래프
  report [--scope] / verify / summary / replay

기능 추가·계층 변경·실행·거래·배포 없음. VALIDATION ≠ MUTATION · INTEGRATION ≠ EXECUTION.
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
    from jarvis.system_integration.engine import SystemIntegrationEngine
    return SystemIntegrationEngine()


def _cmd_validate(a) -> int:
    res = _eng().run_full_validation("SYSTEM", _now(), commit=a.commit)
    _p({"committed": a.commit, "all_passed": res["all_passed"],
        "validation": res["validation"], "findings": res["findings"]})
    return 0 if res["all_passed"] else 1


def _cmd_architecture(a) -> int:
    _p(_eng().architecture_summary())
    return 0


def _cmd_dependencies(a) -> int:
    _p(_eng().dependency_graph())
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.system_integration.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.system_integration.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.system_integration")
    sub = ap.add_subparsers(dest="cmd", required=True)

    va = sub.add_parser("validate")
    va.add_argument("--commit", action="store_true")

    sub.add_parser("architecture")
    sub.add_parser("dependencies")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")

    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")

    args = ap.parse_args(argv)
    disp = {"validate": _cmd_validate, "architecture": _cmd_architecture,
            "dependencies": _cmd_dependencies, "report": _cmd_report, "verify": _cmd_verify,
            "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
