"""`python -m jarvis.security_audit <cmd>` — 최종 보안 감사 CLI. **감사 전용.**

  audit                    전체 보안 감사(원장·아키텍처·런타임) [--commit]
  targets                  감사 대상 계층 목록
  report [--scope] / verify / summary / replay
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
    from jarvis.security_audit.engine import SecurityAuditEngine
    return SecurityAuditEngine()


def _cmd_audit(a) -> int:
    res = _eng().run_full_audit("SYSTEM", _now(), commit=a.commit)
    _p({"committed": a.commit, "all_secure": res["all_secure"], "audit": res["audit"]})
    return 0 if res["all_secure"] else 1


def _cmd_targets(a) -> int:
    from jarvis.security_audit.models import AUDIT_TARGETS
    _p({"targets": list(AUDIT_TARGETS), "count": len(AUDIT_TARGETS)})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "SYSTEM", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.security_audit.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def _cmd_replay(a) -> int:
    from jarvis.security_audit.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.security_audit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    au = sub.add_parser("audit")
    au.add_argument("--commit", action="store_true")
    sub.add_parser("targets")
    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="SYSTEM")
    rp.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"audit": _cmd_audit, "targets": _cmd_targets, "report": _cmd_report,
            "verify": _cmd_verify, "summary": _cmd_summary, "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
