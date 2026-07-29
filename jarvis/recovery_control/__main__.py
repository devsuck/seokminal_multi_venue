"""`python -m jarvis.recovery_control <cmd>` — 복구 관제 CLI. **복구 관제 전용.**

  check [--commit]                     관측 → RecoveryReadinessReport(--commit 기록)
  status                               최신 준비도·원장 건수 요약
  verify                               4개 원장 해시체인·변조·중복 검증
  replay                               동일 입력 재평가(결정성 확인)
  attest --operator O --incident I --decision {APPROVE_RESTART_REVIEW,REJECT} [--reason R] [--commit]
                                       Operator 증언 기록(권한상승 아님)

읽기전용 — 서비스 재시작·킬스위치 해제·거래 재개·브로커/집행/게이트웨이 없음. 거래 승인 아님.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_check(commit: bool) -> int:
    from jarvis.recovery_control.engine import RecoveryControlEngine
    res = RecoveryControlEngine().check(_now(), commit=commit)
    res["note"] = "복구 준비도 관측만 — 자동 복구 아님·재시작/킬해제/거래재개/집행/브로커 없음"
    print(json.dumps({"committed": commit, "result": res},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.recovery_control import ledger
    last = ledger.readiness_head()
    print(json.dumps({
        "latest_readiness": last.get("overall_status") if last else None,
        "latest_emergency_state": last.get("emergency_state") if last else None,
        "evidence": len(ledger.read_evidence()),
        "checklists": len(ledger.read_checklists()),
        "readiness_reports": len(ledger.read_readiness()),
        "attestations": len(ledger.read_attestations()),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.recovery_control.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay() -> int:
    from jarvis.recovery_control.engine import RecoveryControlEngine
    from jarvis.recovery_control.verify import replay
    print(json.dumps(replay(RecoveryControlEngine(), _now()),
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_attest(operator: str, incident: str, decision: str, reason: str, commit: bool) -> int:
    from jarvis.recovery_control.engine import RecoveryControlEngine
    from jarvis.recovery_control.models import RecoveryAttestationError
    eng = RecoveryControlEngine()
    eng.assess(_now(), commit=commit)   # 증언 전 최신 준비도 확보
    try:
        att = eng.attest(operator, incident, decision, _now(), reason=reason, commit=commit)
    except RecoveryAttestationError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"committed": commit, "attestation": att.to_dict()},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.recovery_control")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    sub.add_parser("replay")
    a = sub.add_parser("attest")
    a.add_argument("--operator", required=True)
    a.add_argument("--incident", required=True)
    a.add_argument("--decision", required=True,
                   choices=["APPROVE_RESTART_REVIEW", "REJECT"])
    a.add_argument("--reason", default="")
    a.add_argument("--commit", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args.commit)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    if args.cmd == "replay":
        return _cmd_replay()
    if args.cmd == "attest":
        return _cmd_attest(args.operator, args.incident, args.decision, args.reason, args.commit)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
