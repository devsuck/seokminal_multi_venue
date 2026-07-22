"""`python -m jarvis.broker_readonly <cmd>` — 읽기전용 브로커 CLI. 주문 능력 없음.

  status [--provider ib|kis|mock]      계좌/포지션/헬스(읽기)
  reconcile [--provider ...] [--commit] paper vs broker 대조

  --commit  읽기 쿼리를 broker_readonly_events.jsonl에 감사기록
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _provider(name: str, now: str):
    from jarvis.broker_readonly.adapters import (
        IBReadOnlyProvider,
        KISReadOnlyProvider,
        MockBrokerProvider,
    )
    if name == "kis":
        return KISReadOnlyProvider(now)
    if name == "mock":
        return MockBrokerProvider(timestamp=now)   # 빈 mock(주입 없음)
    return IBReadOnlyProvider(now)


def _cmd_status(provider: str, commit: bool) -> int:
    now = _now()
    prov = _provider(provider, now)
    acct = prov.account_snapshot()
    positions = [p.to_dict() for p in prov.positions()]
    health = prov.health_check().to_dict()
    out = {"provider": prov.source_name, "as_of": now,
           "account": acct.to_dict() if acct else None, "positions": positions,
           "health": health, "note": "read-only — 주문/write 능력 없음"}
    if commit:
        from jarvis.broker_readonly.audit import record_query
        record_query(prov.source_name, "status", now, out)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_reconcile(provider: str, commit: bool) -> int:
    now = _now()
    prov = _provider(provider, now)
    from jarvis.broker_readonly.reconcile import reconcile
    from jarvis.paper_execution.ledger import current_positions
    paper = list(current_positions().values())
    rep = reconcile(paper, prov.positions(), now)
    out = rep.to_dict()
    out["provider"] = prov.source_name
    out["note"] = "read-only 대조 — 주문 없음"
    if commit:
        from jarvis.broker_readonly.audit import record_query
        record_query(prov.source_name, "reconcile", now, out)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.broker_readonly")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--provider", default="ib", choices=["ib", "kis", "mock"])
    s.add_argument("--commit", action="store_true")
    r = sub.add_parser("reconcile")
    r.add_argument("--provider", default="ib", choices=["ib", "kis", "mock"])
    r.add_argument("--commit", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "status":
        return _cmd_status(args.provider, args.commit)
    if args.cmd == "reconcile":
        return _cmd_reconcile(args.provider, args.commit)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
