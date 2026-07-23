"""`python -m jarvis.emergency <cmd>` — 비상 대응 CLI. **비상 결정 전용.**

  check [--commit]   관측 입력(P9.1/P8.5/P9.2 원장) → EmergencyDecision(--commit 기록)
  status             현재 비상 상태·원장 건수 요약
  verify             4개 원장 해시체인·변조·중복 검증
  replay             동일 입력 재판정(결정성 확인)
  summary            비상 상태 분포·복구 흐름 집계

읽기전용 — Gateway/Broker/Order Cancel/ARM/Kill Switch 작동 없음. 거래를 승인하지 않음.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_check(commit: bool) -> int:
    from jarvis.emergency.engine import EmergencyEngine
    res = EmergencyEngine().check(now=_now(), commit=commit)
    res["note"] = "비상 결정만 — 실제 킬스위치 작동 아님·집행/주문/브로커/게이트웨이 없음"
    print(json.dumps({"committed": commit, "result": res},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.emergency import ledger
    from jarvis.emergency.engine import EmergencyEngine
    print(json.dumps({
        "current_state": EmergencyEngine().current_state(),
        "decisions": len(ledger.read_decisions()),
        "recovery_requests": len(ledger.read_recovery_requests()),
        "recovery_approvals": len(ledger.read_recovery_approvals()),
        "recovery_events": len(ledger.read_recovery_events()),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.emergency.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay() -> int:
    from jarvis.emergency.engine import EmergencyEngine
    from jarvis.emergency.verify import replay
    print(json.dumps(replay(EmergencyEngine(), now=_now()),
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_summary() -> int:
    from jarvis.emergency import ledger
    dist: dict = {}
    for d in ledger.read_decisions():
        dist[d.get("emergency_state")] = dist.get(d.get("emergency_state"), 0) + 1
    print(json.dumps({
        "state_distribution": dict(sorted(dist.items())),
        "n_decisions": len(ledger.read_decisions()),
        "recovery": {"requests": len(ledger.read_recovery_requests()),
                     "approvals": len(ledger.read_recovery_approvals()),
                     "events": len(ledger.read_recovery_events())},
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.emergency")
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
