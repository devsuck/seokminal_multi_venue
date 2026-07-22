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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.portfolio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("matrix")
    args = ap.parse_args(argv)
    if args.cmd == "matrix":
        return _cmd_matrix()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
