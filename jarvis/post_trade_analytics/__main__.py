"""`python -m jarvis.post_trade_analytics <cmd>` — 사후 집행분석 CLI. **ANALYTICS-ONLY.**

  analyze [--commit]   합성 예시 집행 분석 → TCA 리포트(데모)
  status               분석 원장 요약(리포트 수·상태 분포)
  verify               해시체인 무결성 검증
  replay               체인 재검증(결정적)
  summary              합성 포트폴리오 집계(데모)

읽기전용 — 주문/집행/브로커 호출/상태변경 없음. 거래를 승인하지 않음.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _demo_execution():
    from jarvis.post_trade_analytics.models import ExecutionData
    return ExecutionData(
        request_id="PTA:demo", symbol="DEMO", side="BUY", order_quantity=100.0,
        fills=[{"fill_id": "F:1", "quantity": 40.0, "fill_price": 100.0, "fee": 0.0,
                "timestamp": "2026-07-22T00:00:01Z"},
               {"fill_id": "F:2", "quantity": 60.0, "fill_price": 100.2, "fee": 0.0,
                "timestamp": "2026-07-22T00:00:03Z"}],
        arrival_price=100.0, decision_price=99.9, close_price=100.3, mid_price=100.05,
        start_time="2026-07-22T00:00:00Z", end_time="2026-07-22T00:00:05Z",
        broker="mock", strategy="DEMO")


def _cmd_analyze(commit: bool) -> int:
    from jarvis.post_trade_analytics.engine import PostTradeAnalyticsEngine
    now = _now()
    r = PostTradeAnalyticsEngine().analyze("PTA:demo", _demo_execution(), now, commit=commit)
    out = r.to_dict()
    out["note"] = "사후 분석만 — 거래 승인 아님·집행/주문/브로커 없음(합성 예시)"
    print(json.dumps({"committed": commit, "report": out}, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.post_trade_analytics.ledger import last_report, read_reports
    reps = read_reports()
    dist: dict = {}
    for r in reps:
        dist[r.get("overall_status")] = dist.get(r.get("overall_status"), 0) + 1
    print(json.dumps({"n_reports": len(reps), "status_distribution": dist,
                      "last_report": last_report()}, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.post_trade_analytics.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay() -> int:
    from jarvis.post_trade_analytics.engine import PostTradeAnalyticsEngine
    from jarvis.post_trade_analytics.verify import replay, verify_chain
    res = replay(PostTradeAnalyticsEngine(), "PTA:demo", _demo_execution())
    print(json.dumps({"chain": verify_chain(), "replay": res},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_summary() -> int:
    from jarvis.post_trade_analytics.engine import PostTradeAnalyticsEngine
    trades = [{"request_id": "A", "cost_bps": 12.0, "slippage_bps": 8.0, "fill_quality": 0.9,
               "success": True, "broker": "mock", "symbol": "DEMO", "strategy": "S1"},
              {"request_id": "B", "cost_bps": 30.0, "slippage_bps": 20.0, "fill_quality": 0.6,
               "success": True, "broker": "ib", "symbol": "DEMO", "strategy": "S2"}]
    s = PostTradeAnalyticsEngine().portfolio_summary(trades, "daily", _now())
    print(json.dumps(s.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.post_trade_analytics")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    return {"analyze": lambda: _cmd_analyze(args.commit), "status": _cmd_status,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}[args.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
