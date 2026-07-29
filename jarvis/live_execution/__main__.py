"""`python -m jarvis.live_execution <cmd>` — 사람 게이트 라이브 집행 CLI.

  submit [--broker mock|ib|kis] [--commit]   READY 인증서 + 사람 ARM인 의도만 제출
  status                                      집행 요청/응답 요약
  verify                                      결정적 응답 해시(동일입력 → 동일해시)

**사람의 명시적 호출로만 동작 — 자율/스케줄러/무인 실행 아님.** 기본 읽기전용(dry-run);
--commit 시에만 원장 기록. 실브로커(IB/KIS)는 기본 비활성(자격증명 없음·자율레벨 미달).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ready_certificates() -> dict:
    """READY 인증서(P7.7) intent_id → cert."""
    from jarvis.execution_readiness.ledger import read_certificates
    out = {}
    for c in read_certificates():
        if c.get("status") == "READY":
            out[c.get("intent_id")] = c
    return out


def _intents() -> dict:
    from jarvis.execution_control.ledger import read_intents
    from jarvis.execution_control.models import ExecutionIntent
    out = {}
    for row in read_intents():
        i = ExecutionIntent(**{k: row[k] for k in (
            "intent_id", "strategy", "symbol", "side", "quantity", "target_weight",
            "source_proposal_id", "created_at", "expiry") if k in row})
        out[i.intent_id] = i
    return out


def _cmd_submit(broker: str, commit: bool) -> int:
    from jarvis.live_execution.adapters import get_adapter
    from jarvis.live_execution.engine import LiveExecutionEngine, build_request, human_arm
    now = _now()
    eng = LiveExecutionEngine()
    adapter = get_adapter(broker)
    certs = _ready_certificates()
    intents = _intents()
    out = []
    for iid, cert in certs.items():
        intent = intents.get(iid)
        arm = human_arm(iid)          # 사람 ARM 필수
        if intent is None or arm is None:
            continue
        arm_id = arm.get("arm_id", arm.get("armed_by", "human"))
        req = build_request(intent, arm_id, broker, now)
        resp = eng.submit(req, cert, adapter, now, commit=commit)
        if resp is not None:
            out.append(resp.to_dict())
    accepted = sum(1 for r in out if r["status"] == "ACCEPTED")
    print(json.dumps({"broker": broker, "submitted": len(out), "accepted": accepted,
                      "rejected": len(out) - accepted, "committed": commit, "responses": out,
                      "note": "사람 게이트 집행 — 자율/무인 아님. 실브로커는 기본 비활성."},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.live_execution.ledger import last_response, read_events, read_requests, read_responses
    from jarvis.live_execution.adapters import IBExecutionAdapter, KISExecutionAdapter, MockExecutionAdapter
    print(json.dumps({
        "n_requests": len(read_requests()), "n_responses": len(read_responses()),
        "n_events": len(read_events()), "last_response": last_response(),
        "adapters": {"mock": MockExecutionAdapter().health_check(),
                     "ib": IBExecutionAdapter().health_check(),
                     "kis": KISExecutionAdapter().health_check()}},
        ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.execution_control.models import ExecutionIntent
    from jarvis.execution_readiness.models import ExecutionReadinessCertificate
    from jarvis.live_execution.adapters import MockExecutionAdapter
    from jarvis.live_execution.engine import LiveExecutionEngine, build_request
    now = "2026-07-22T00:00:00Z"
    intent = ExecutionIntent("EI:verify", "DEMO", "DEMO", "BUY", 10.0, 0.3, "PP:verify", now, "")
    cert = ExecutionReadinessCertificate(certificate_id="CERT:verify", status="READY",
                                         intent_id="EI:verify", created_at=now)
    eng = LiveExecutionEngine()
    req = build_request(intent, "ARM:verify", "mock", now)
    r1 = eng.submit(req, cert, MockExecutionAdapter(), now, arm_present=True, market_fresh=True)
    r2 = eng.submit(req, cert, MockExecutionAdapter(), now, arm_present=True, market_fresh=True)
    ok = r1.response_hash == r2.response_hash and r1.to_dict() == r2.to_dict()
    print(json.dumps({"ok": ok, "deterministic": ok, "status": r1.status,
                      "broker_order_id": r1.broker_order_id, "hash": r1.response_hash},
                     ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.live_execution")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit")
    s.add_argument("--broker", default="mock", choices=["mock", "ib", "kis"])
    s.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "submit":
        return _cmd_submit(args.broker, args.commit)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
