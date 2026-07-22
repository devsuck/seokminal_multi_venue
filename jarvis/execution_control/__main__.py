"""`python -m jarvis.execution_control <cmd>` — 통제된 의도 CLI. 집행/주문 없음.

  create [--commit]   APPROVED 제안 → ExecutionIntent(의도 후보)
  check [--commit]    의도 → ExecutionDecision(6검사, BLOCKED/READY)
  status              최근 의도/결정 이벤트
  verify              결정적 해시(동일입력 → 동일해시)

기본 읽기전용. --commit 시에만 append-only 원장 기록. **주문 생성 절대 없음.**
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _approved_proposals(now: str) -> list[dict]:
    from jarvis.production.approval import proposal_status, read_approvals, read_proposals
    apps = read_approvals()
    return [p for p in read_proposals() if proposal_status(p, apps, now) == "APPROVED"]


def _cmd_create(commit: bool) -> int:
    from jarvis.execution_control.engine import ExecutionControlPlane
    now = _now()
    cp = ExecutionControlPlane()
    out = []
    for prop in _approved_proposals(now):
        intent = cp.build_intent(prop, now, commit=commit)
        if intent is not None:
            out.append(intent.to_dict())
    print(json.dumps({"created": len(out), "committed": commit, "intents": out,
                      "note": "의도 후보 — 주문 아님·집행 없음"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_check(commit: bool) -> int:
    from jarvis.execution_control.engine import ExecutionControlPlane
    from jarvis.execution_control.ledger import read_intents
    from jarvis.execution_control.models import ExecutionIntent
    now = _now()
    cp = ExecutionControlPlane()
    out = []
    for row in read_intents():
        intent = ExecutionIntent(**{k: row[k] for k in (
            "intent_id", "strategy", "symbol", "side", "quantity", "target_weight",
            "source_proposal_id", "created_at", "expiry") if k in row})
        decision = cp.evaluate(intent, now, commit=commit)
        out.append(decision.to_dict())
    ready = sum(1 for d in out if d["status"] == "READY")
    print(json.dumps({"evaluated": len(out), "ready": ready, "blocked": len(out) - ready,
                      "committed": commit, "decisions": out,
                      "note": "READY는 지시 후보일 뿐 — 주문/집행 아님"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.execution_control.ledger import read_decisions, read_events, read_intents
    ints, decs, evs = read_intents(), read_decisions(), read_events()
    print(json.dumps({"n_intents": len(ints), "n_decisions": len(decs), "n_events": len(evs),
                      "last_event": evs[-1] if evs else None},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.execution_control.engine import ExecutionControlPlane
    now = "2026-07-22T00:00:00Z"
    prop = {"proposal_id": "PP:verify", "source": "demo", "strategy": "DEMO",
            "allocation": {"DEMO": 0.3}, "created_at": now}
    cp = ExecutionControlPlane()
    i = cp.build_intent(prop, now, commit=False)
    # 동일 주입값 → 동일 결정/해시
    kw = dict(approved=True, gate_allow=False, risk_ok=False,
              reconciliation_severity="OK", data_fresh=False, arm_present=False)
    d1 = cp.evaluate(i, now, **kw)
    d2 = cp.evaluate(i, now, **kw)
    ok = d1.hash == d2.hash and d1.to_dict() == d2.to_dict()
    print(json.dumps({"ok": ok, "deterministic": ok, "status": d1.status,
                      "blockers": d1.blockers, "hash": d1.hash},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.execution_control")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--commit", action="store_true")
    k = sub.add_parser("check")
    k.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "create":
        return _cmd_create(args.commit)
    if args.cmd == "check":
        return _cmd_check(args.commit)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
