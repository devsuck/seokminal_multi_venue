"""`python -m jarvis.portfolio <cmd>` — Return Matrix CLI 검증.

  matrix   실 buyback 원장 → StrategyReturnSeries 요약 + 상관(활동전략)
"""
from __future__ import annotations

import argparse
import json


def _cmd_matrix() -> int:
    from jarvis.portfolio.returns_matrix import ReturnMatrix, buyback_source
    m = ReturnMatrix([buyback_source()], capacity=1.0)
    series = m.build()
    cal = m.calendar()
    out = {
        "n_dates": len(cal),
        "calendar_span": [cal[0], cal[-1]] if cal else None,
        "strategies": {sid: s.summary() for sid, s in series.items()},
        "active_strategies": [sid for sid, s in series.items() if s.active],
        "avg_pairwise_correlation": m.correlation(),
        "note": "P1.7 표준화 레이어 — 배분 없음. P2 Meta Portfolio 입력용.",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_allocate(write: bool) -> int:
    from datetime import datetime, timezone
    from jarvis.portfolio.allocator import RiskConstraints, propose_allocation
    from jarvis.portfolio.returns_matrix import ReturnMatrix, buyback_source
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    m = ReturnMatrix([buyback_source()], capacity=1.0)
    res = propose_allocation(m, RiskConstraints(), ts=ts)
    out = res.to_dict()
    out["note"] = "제안 전용 — 집행 아님. 활동 전략 <2면 폴백."
    if write:
        from jarvis.portfolio.allocation_ledger import write_proposal
        out["ledger"] = write_proposal(res)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.portfolio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("matrix")
    a = sub.add_parser("allocate")
    a.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "matrix":
        return _cmd_matrix()
    if args.cmd == "allocate":
        return _cmd_allocate(args.write)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
