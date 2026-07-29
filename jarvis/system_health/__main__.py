"""`python -m jarvis.system_health <cmd>` — 시스템 헬스 관측 CLI. **OPERATIONS-ONLY.**

  check [--commit]   전 서브시스템 관측 → SystemHealthReport(원장 기록은 --commit)
  status             헬스 원장 요약(리포트 수·최근 overall/score)
  verify             해시체인 무결성·변조 검증
  replay             동일 관측 재현(결정성 확인)
  summary            최근 리포트의 서브시스템 상태 분포

읽기전용 — 주문/집행/브로커 호출/상태변경 없음. 거래를 승인하지 않음.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_check(commit: bool) -> int:
    from jarvis.system_health.engine import SystemHealthEngine
    r = SystemHealthEngine().check(_now(), commit=commit)
    out = r.to_dict()
    out["note"] = "헬스 관측만 — 거래 승인 아님·집행/주문/브로커 없음"
    print(json.dumps({"committed": commit, "report": out},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.system_health.ledger import last_report, read_reports
    reps = read_reports()
    last = last_report()
    print(json.dumps({
        "n_reports": len(reps),
        "last_overall_status": last.get("overall_status") if last else None,
        "last_health_score": last.get("health_score") if last else None,
        "last_report_id": last.get("report_id") if last else None,
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.system_health.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay() -> int:
    from jarvis.system_health.engine import SystemHealthEngine
    from jarvis.system_health.verify import replay, verify_chain
    res = replay(SystemHealthEngine(), _now())
    print(json.dumps({"chain": verify_chain(), "replay": res},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_summary() -> int:
    from jarvis.system_health.engine import SystemHealthEngine
    r = SystemHealthEngine().check(_now())
    print(json.dumps({"overall_status": r.overall_status, "health_score": r.health_score,
                      "summary": r.summary}, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.system_health")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    return {"check": lambda: _cmd_check(args.commit), "status": _cmd_status,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}[args.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
