"""`python -m jarvis.execution_cost <cmd>` — 집행비용 회계 CLI. 집행/주문/write 없음.

  calculate [--commit]   합성 예시로 비용 리포트 산출(데모)
  status                 비용 원장 요약(이벤트 수·상태 분포)
  verify                 해시체인 무결성 검증
  replay                 체인 재검증(결정적)

읽기전용 — 어떤 것도 변경/집행하지 않음. 브로커 write 없음.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_calculate(commit: bool) -> int:
    from jarvis.execution_cost.engine import CostAccountingEngine
    from jarvis.execution_cost.models import CostRates, CostThresholds, ExecutionCostInput
    now = _now()
    # 합성 예시(데모): BUY 100주, 기대가 100, 체결가 100.1
    gross = round(100.0 * 100.1, 8)
    inp = ExecutionCostInput(order_id="ECR:demo", symbol="DEMO", side="BUY", quantity=100.0,
                             expected_price=100.0, fill_price=100.1, gross_value=gross,
                             timestamp=now)
    eng = CostAccountingEngine(CostRates(commission_rate=0.0005, exchange_fee_rate=0.0001),
                               CostThresholds(expected_cost_bps=10.0))
    r = eng.calculate(inp, now, mid_price=100.05, commit=commit)
    out = r.to_dict()
    out["note"] = "회계 관측만 — 집행/주문/브로커 write 없음(합성 예시)"
    print(json.dumps({"committed": commit, "report": out}, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.execution_cost.ledger import last_event, read_events
    evs = read_events()
    dist: dict = {}
    for e in evs:
        dist[e.get("status")] = dist.get(e.get("status"), 0) + 1
    print(json.dumps({"n_events": len(evs), "status_distribution": dist, "last_event": last_event()},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.execution_cost.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay() -> int:
    from jarvis.execution_cost.ledger import read_events
    from jarvis.execution_cost.verify import verify_chain
    chain = verify_chain()
    hashes = [e.get("cost_hash") for e in read_events()]
    print(json.dumps({"chain": chain, "n": len(hashes), "cost_hashes": hashes},
                     ensure_ascii=False, indent=2, default=str))
    return 0 if chain["ok"] else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.execution_cost")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calculate")
    c.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    if args.cmd == "calculate":
        return _cmd_calculate(args.commit)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    if args.cmd == "replay":
        return _cmd_replay()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
