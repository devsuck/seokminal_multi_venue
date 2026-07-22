"""`python -m jarvis.reconciliation <cmd>` — 읽기전용 대조 CLI. 집행 없음.

  check [--broker ib|kis|mock] [--commit]   페이퍼 vs 브로커 vs 라이브 대조
  status                                     최근 대조 이벤트
  verify                                     결정적 리포트(동일입력→동일해시)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _broker(name: str, now: str):
    from jarvis.broker_readonly.adapters import (
        IBReadOnlyProvider,
        KISReadOnlyProvider,
        MockBrokerProvider,
    )
    if name == "kis":
        return KISReadOnlyProvider(now)
    if name == "mock":
        return MockBrokerProvider(timestamp=now)
    return IBReadOnlyProvider(now)


def _live(now: str):
    from jarvis.live_market_data.cache import CacheStreamingProvider
    return CacheStreamingProvider(clock=now)


def _cmd_check(broker: str, commit: bool) -> int:
    from jarvis.reconciliation.engine import reconcile_runtime
    now = _now()
    report = reconcile_runtime(_broker(broker, now), _live(now), now, commit=commit)
    out = report.to_dict()
    out["note"] = "read-only 대조 — 집행/주문/변경 없음"
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.reconciliation.ledger import last_event, read_events
    print(json.dumps({"n_events": len(read_events()), "last": last_event()},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.reconciliation.engine import ReconciliationEngine
    from jarvis.reconciliation.ledger import report_hash
    # 고정 합성 입력 → 두 번 → 동일 해시
    paper = [{"strategy_id": "A", "quantity": 10, "average_price": 100, "market_value": 1100}]
    broker = [{"symbol": "A", "quantity": 8, "avg_price": 100, "market_value": 880}]
    eng = ReconciliationEngine()
    r1 = eng.reconcile(paper, broker, paper_nav=11000, broker_equity=10000, now="2026-07-22T00:00:00Z")
    r2 = eng.reconcile(paper, broker, paper_nav=11000, broker_equity=10000, now="2026-07-22T00:00:00Z")
    ok = report_hash(r1) == report_hash(r2)
    print(json.dumps({"ok": ok, "deterministic": ok, "severity": r1.severity,
                      "hash": report_hash(r1)}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.reconciliation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--broker", default="ib", choices=["ib", "kis", "mock"])
    c.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args.broker, args.commit)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
