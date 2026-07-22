"""`python -m jarvis.execution_readiness <cmd>` — 집행 준비 인증 CLI. 집행/주문 없음.

  check [--commit]   의도별 모든 통제 레이어 집계 → 인증서(READY/BLOCKED)
  status             인증 원장 요약
  verify             결정적 해시(동일입력 → 동일해시)

기본 읽기전용. --commit 시에만 append-only 원장 기록.
**인증서는 거래 허가가 아님 — 프리플라이트 통과 진술만. 실주문/집행 절대 없음.**
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_intents() -> list:
    from jarvis.execution_control.ledger import read_intents
    from jarvis.execution_control.models import ExecutionIntent
    out = []
    for row in read_intents():
        out.append(ExecutionIntent(**{k: row[k] for k in (
            "intent_id", "strategy", "symbol", "side", "quantity", "target_weight",
            "source_proposal_id", "created_at", "expiry") if k in row}))
    return out


def _cmd_check(commit: bool) -> int:
    from jarvis.execution_readiness.engine import ExecutionReadinessEngine
    now = _now()
    eng = ExecutionReadinessEngine()
    out = []
    for intent in _load_intents():
        cert = eng.certify(intent, now, commit=commit)
        out.append(cert.to_dict())
    ready = sum(1 for c in out if c["status"] == "READY")
    print(json.dumps({"certified": len(out), "ready": ready, "blocked": len(out) - ready,
                      "committed": commit, "certificates": out,
                      "note": "인증서는 거래 허가 아님 — 프리플라이트 통과 진술만"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.execution_readiness.ledger import last_certificate, read_certificates, read_events
    print(json.dumps({"n_certificates": len(read_certificates()), "n_events": len(read_events()),
                      "last_certificate": last_certificate()},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.execution_control.models import ExecutionIntent
    from jarvis.execution_readiness.engine import ExecutionReadinessEngine
    now = "2026-07-22T00:00:00Z"
    intent = ExecutionIntent(intent_id="EI:verify", strategy="DEMO", symbol="DEMO",
                             side="BUY", quantity=0.0, target_weight=0.3,
                             source_proposal_id="PP:verify", created_at=now, expiry="")
    eng = ExecutionReadinessEngine()
    kw = dict(approval=True, control_ready=True, risk_ok=True, arm_present=False,
              broker_ok=False, market_ok=False, simulation_pass=False, reconciliation_ok=False)
    c1 = eng.certify(intent, now, **kw)
    c2 = eng.certify(intent, now, **kw)
    ok = c1.hash == c2.hash and c1.to_dict() == c2.to_dict()
    print(json.dumps({"ok": ok, "deterministic": ok, "status": c1.status,
                      "blockers": c1.blockers, "hash": c1.hash},
                     ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.execution_readiness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args.commit)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
