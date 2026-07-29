"""`python -m jarvis.execution_reconciliation <cmd>` — 집행 결과 검증 CLI. 집행/주문 없음.

  check [--commit]   시뮬 리포트 → 의도 기대값 대비 검증(PASS/WARNING/FAILED)
  status             검증 원장 요약
  verify             결정적 해시(동일입력 → 동일해시)

기본 읽기전용. --commit 시에만 append-only 원장 기록. **실주문/집행 절대 없음.**
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_check(commit: bool) -> int:
    from jarvis.execution_reconciliation.engine import (
        ExecutionReconciliationEngine,
        perfect_expectation,
    )
    from jarvis.execution_simulation.ledger import read_reports as read_sim_reports
    now = _now()
    eng = ExecutionReconciliationEngine()
    out = []
    for sim in read_sim_reports():
        if sim.get("status") != "SIMULATED" or not sim.get("order") or not sim.get("fill"):
            continue
        intent_time = sim["order"].get("created_at", now)
        exp = perfect_expectation(sim, intent_time)
        report = eng.validate(exp, sim, now, commit=commit)
        out.append(report.to_dict())
    passed = sum(1 for r in out if r["status"] == "PASS")
    print(json.dumps({"validated": len(out), "pass": passed,
                      "warning": sum(1 for r in out if r["status"] == "WARNING"),
                      "failed": sum(1 for r in out if r["status"] == "FAILED"),
                      "committed": commit, "reports": out,
                      "note": "결과 검증만 — 주문/집행/실자본 아님"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.execution_reconciliation.ledger import last_report, read_events, read_reports
    print(json.dumps({"n_reports": len(read_reports()), "n_events": len(read_events()),
                      "last_report": last_report()},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.execution_reconciliation.engine import (
        ExecutionReconciliationEngine,
        perfect_expectation,
    )
    now = "2026-07-22T00:00:00Z"
    # 고정 합성 시뮬 리포트 → 완전일치 기대 → 두 번 → 동일 해시
    sim = {"simulation_id": "SIM:verify", "status": "SIMULATED",
           "order": {"simulation_id": "SIM:verify", "intent_id": "EI:verify", "symbol": "DEMO",
                     "side": "BUY", "quantity": 100.0, "reference_price": 100.0, "created_at": now},
           "fill": {"simulation_id": "SIM:verify", "fill_price": 100.1, "filled_quantity": 100.0,
                    "slippage": 0.1, "fees": 5.005, "timestamp": now},
           "assumptions": {"slippage_bps": 10.0, "fee_bps": 5.0, "reference_price": 100.0}}
    eng = ExecutionReconciliationEngine()
    exp = perfect_expectation(sim, now)
    r1 = eng.validate(exp, sim, now)
    r2 = eng.validate(exp, sim, now)
    ok = r1.hash == r2.hash and r1.to_dict() == r2.to_dict()
    print(json.dumps({"ok": ok, "deterministic": ok, "status": r1.status,
                      "deviations": r1.deviations, "hash": r1.hash},
                     ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.execution_reconciliation")
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
