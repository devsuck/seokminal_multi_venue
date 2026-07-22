"""`python -m jarvis.execution_simulation <cmd>` — 가상 체결 시뮬 CLI. 집행/주문 없음.

  run [--commit] [--slippage-bps N] [--fee-bps N]   READY 결정 → 가상 체결 시뮬
  status                                            시뮬 원장 요약
  verify                                            결정적 해시(동일입력 → 동일해시)

기본 읽기전용. --commit 시에만 append-only 원장 기록. **실주문 절대 없음.**
가격/수량은 시뮬 가정(주입) — 실자본 이동 아님.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

# 시뮬 명목(가정) — 목표비중 → 가상수량 환산 기준. 실자본 아님.
_SIM_NOTIONAL = 1_000_000.0
_SYNTHETIC_PRICE = 100.0


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _synthetic_price(symbol: str, now: str) -> float:
    return _SYNTHETIC_PRICE   # 결정적 합성 참조가(시뮬 가정)


def _load_intents() -> dict:
    from jarvis.execution_control.ledger import read_intents
    from jarvis.execution_control.models import ExecutionIntent
    out = {}
    for row in read_intents():
        i = ExecutionIntent(**{k: row[k] for k in (
            "intent_id", "strategy", "symbol", "side", "quantity", "target_weight",
            "source_proposal_id", "created_at", "expiry") if k in row})
        out[i.intent_id] = i
    return out


def _ready_intents() -> list:
    """execution_control 결정 원장에서 READY만 → 해당 intent 반환."""
    from jarvis.execution_control.ledger import read_decisions
    intents = _load_intents()
    ready_ids = [d["intent_id"] for d in read_decisions() if d.get("status") == "READY"]
    return [intents[i] for i in ready_ids if i in intents]


class _ReadyDecision:
    status = "READY"


def _cmd_run(commit: bool, slippage_bps: float, fee_bps: float) -> int:
    from jarvis.execution_simulation.engine import SimulationEngine
    now = _now()
    eng = SimulationEngine()
    reports = []
    for intent in _ready_intents():
        ref = _synthetic_price(intent.symbol, now)
        qty = round(abs(float(intent.target_weight)) * _SIM_NOTIONAL / ref, 8)
        r = eng.simulate(intent, _ReadyDecision(), _synthetic_price, now,
                         quantity=qty, slippage_bps=slippage_bps, fee_bps=fee_bps,
                         commit=commit)
        if r is not None:
            reports.append(r.to_dict())
    print(json.dumps({"simulated": len(reports), "committed": commit,
                      "slippage_bps": slippage_bps, "fee_bps": fee_bps, "reports": reports,
                      "note": "가상 체결 — 주문/집행/실자본 아님"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.execution_simulation.ledger import read_fills, read_orders, read_reports
    orders, fills, reports = read_orders(), read_fills(), read_reports()
    print(json.dumps({"n_orders": len(orders), "n_fills": len(fills),
                      "n_reports": len(reports),
                      "last_report": reports[-1] if reports else None},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.execution_control.models import ExecutionIntent
    from jarvis.execution_simulation.engine import SimulationEngine
    now = "2026-07-22T00:00:00Z"
    intent = ExecutionIntent(intent_id="EI:verify", strategy="DEMO", symbol="DEMO",
                             side="BUY", quantity=100.0, target_weight=0.3,
                             source_proposal_id="PP:verify", created_at=now, expiry="")
    eng = SimulationEngine()
    r1 = eng.simulate(intent, _ReadyDecision(), _synthetic_price, now,
                      slippage_bps=10.0, fee_bps=5.0)
    r2 = eng.simulate(intent, _ReadyDecision(), _synthetic_price, now,
                      slippage_bps=10.0, fee_bps=5.0)
    ok = r1.hash == r2.hash and r1.to_dict() == r2.to_dict()
    print(json.dumps({"ok": ok, "deterministic": ok, "status": r1.status,
                      "fill_price": r1.fill["fill_price"] if r1.fill else None,
                      "fees": r1.fill["fees"] if r1.fill else None, "hash": r1.hash},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.execution_simulation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--commit", action="store_true")
    r.add_argument("--slippage-bps", type=float, default=0.0)
    r.add_argument("--fee-bps", type=float, default=0.0)
    sub.add_parser("status")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        return _cmd_run(args.commit, args.slippage_bps, args.fee_bps)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
