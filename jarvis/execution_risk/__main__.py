"""`python -m jarvis.execution_risk <cmd>` — 제출 직전 리스크 집행검사 CLI.

  check [--commit]   합성/기본 컨텍스트로 요청 평가(현주소: 브로커/시장 미구성 → BLOCK)
  status             리스크 원장 요약(이벤트 수·상태 분포)
  verify             해시체인 무결성 검증
  replay             체인 재검증(결정적)

읽기전용 — 주문/집행/브로커 호출/상태변경 없음.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_check(commit: bool) -> int:
    from jarvis.execution_risk.engine import ExecutionRiskEngine
    from jarvis.execution_risk.policy import RiskContext
    now = _now()
    # 현주소: 브로커/시장 미구성 → broker_health/market FAILED → BLOCK(honest CLOSED)
    ctx = RiskContext(position_size=0.0, notional=0.0, concentration=0.0,
                      broker_healthy=False, market_fresh=False)
    report = ExecutionRiskEngine().evaluate({"request_id": "XRR:demo"}, ctx, now=now, commit=commit)
    out = report.to_dict()
    out["note"] = "제출 직전 리스크 평가만 — 주문/집행/브로커 write 없음(합성 예시)"
    print(json.dumps({"committed": commit, "report": out}, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.execution_risk.ledger import last_event, read_events
    evs = read_events()
    dist: dict = {}
    for e in evs:
        dist[e.get("overall_status")] = dist.get(e.get("overall_status"), 0) + 1
    print(json.dumps({"n_events": len(evs), "status_distribution": dist, "last_event": last_event()},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.execution_risk.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay() -> int:
    from jarvis.execution_risk.ledger import read_events
    from jarvis.execution_risk.verify import verify_chain
    chain = verify_chain()
    hashes = [e.get("report_hash") for e in read_events()]
    print(json.dumps({"chain": chain, "n": len(hashes), "report_hashes": hashes},
                     ensure_ascii=False, indent=2, default=str))
    return 0 if chain["ok"] else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.execution_risk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--commit", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args.commit)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    if args.cmd == "replay":
        return _cmd_replay()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
