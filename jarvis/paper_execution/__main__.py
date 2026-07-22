"""`python -m jarvis.paper_execution <cmd>` — 시뮬 체결 CLI. 기본 DRY-RUN.

  status              현재 페이퍼 포지션 + 실현/미실현 PnL
  execute [--commit]  APPROVED+ALLOW 프로덕션 제안 소비 → 시뮬 체결
  verify              원장 결정적 재구축 검증
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# 시뮬 가격(플레이스홀더 — 실시장데이터 아님, 결정적)
def _price(strategy: str, ts: str) -> float:
    return 100.0


def _cmd_status() -> int:
    from jarvis.paper_execution.engine import portfolio_status
    print(json.dumps(portfolio_status(), ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_execute(commit: bool) -> int:
    from jarvis.paper_execution.engine import PaperExecutionEngine
    from jarvis.production.approval import proposal_status, read_approvals, read_proposals
    from jarvis.production.gate import read_gate_decisions
    now = _now()
    approvals = read_approvals()
    gate_by_pid = {d["proposal_id"]: d for d in read_gate_decisions()}  # 최신 우선(뒤가 덮음)
    eng = PaperExecutionEngine()
    out = []
    for prop in read_proposals():
        pid = prop["proposal_id"]
        approved = proposal_status(prop, approvals, now) == "APPROVED"
        gate = gate_by_pid.get(pid)
        rep = eng.execute_proposal(prop, approved, gate, _price, now, ts=now, commit=commit)
        out.append({"proposal_id": pid, "strategy": prop.get("strategy"),
                    "orders": rep.orders_created, "note": rep.note})
    print(json.dumps({"as_of": now, "n_proposals": len(out), "results": out,
                      "note": ("제안 전용 파이프라인 → 시뮬 체결. " +
                               ("COMMIT: 원장 기록." if commit else "DRY-RUN: 무기록.")),
                      "reminder": "라이브 아님·브로커 없음·게이트웨이 무호출"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_price() -> int:
    from jarvis.paper_execution.ledger import current_positions
    now = _now()
    positions = list(current_positions().values())
    prov = None
    if positions:
        from jarvis.paper_execution.market_data import FlatMarkProvider
        prov = FlatMarkProvider({p["strategy_id"]: p["average_price"] for p in positions}, now)
    prices = [prov.get(p["strategy_id"], now).to_dict() for p in positions] if prov else []
    print(json.dumps({"as_of": now, "prices": prices,
                      "note": "flat mark @entry (실시장데이터 아님 — 결측 시 평단)"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_valuation(commit: bool) -> int:
    from jarvis.paper_execution.valuation import valuate_current
    snap = valuate_current(_now(), commit=commit)
    out = snap.to_dict()
    out["note"] = "NAV mark-to-market. " + ("COMMIT: paper_portfolio 기록." if commit else "DRY-RUN.")
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_performance() -> int:
    from jarvis.paper_execution.performance import attribution_current
    print(json.dumps(attribution_current(_now()), ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_monitor() -> int:
    from jarvis.paper_execution.monitoring import monitor
    print(json.dumps(monitor(_now()).to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.paper_execution.verify import verify
    res = verify()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res.get("ok") else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.paper_execution")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    e = sub.add_parser("execute")
    e.add_argument("--commit", action="store_true")
    sub.add_parser("price")
    v = sub.add_parser("valuation")
    v.add_argument("--commit", action="store_true")
    sub.add_parser("performance")
    sub.add_parser("monitor")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "execute":
        return _cmd_execute(args.commit)
    if args.cmd == "price":
        return _cmd_price()
    if args.cmd == "valuation":
        return _cmd_valuation(args.commit)
    if args.cmd == "performance":
        return _cmd_performance()
    if args.cmd == "monitor":
        return _cmd_monitor()
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
