"""`python -m jarvis.operations_console <cmd>` — 운영 관제 콘솔 CLI. **읽기전용 뷰.**

  dashboard    System/Incidents/Emergency/Recovery/Audit 요약 텍스트
  status       OperationsSnapshot(JSON)
  timeline     다중 소스 타임라인(시간 정렬, JSON)
  verify       전 감사 원장 체인 무결성

컨트롤 없음 — 명령 실행·재시작·상태변경·킬스위치·복구 실행·주문·브로커 없음. 표시만.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_dashboard() -> int:
    from jarvis.operations_console.engine import OperationsConsole, render_dashboard
    view = OperationsConsole().dashboard(_now())
    print(render_dashboard(view))
    return 0


def _cmd_status() -> int:
    from jarvis.operations_console.engine import OperationsConsole
    snap = OperationsConsole().snapshot(_now()).to_dict()
    snap["note"] = "읽기전용 관제 뷰 — 제어 없음"
    print(json.dumps(snap, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_timeline() -> int:
    from jarvis.operations_console.engine import OperationsConsole
    tl = [e.to_dict() for e in OperationsConsole().timeline()]
    print(json.dumps({"events": tl, "n": len(tl)}, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.operations_console.verify import verify_all
    res = verify_all()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.operations_console")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dashboard")
    sub.add_parser("status")
    sub.add_parser("timeline")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    return {"dashboard": _cmd_dashboard, "status": _cmd_status,
            "timeline": _cmd_timeline, "verify": _cmd_verify}[args.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
