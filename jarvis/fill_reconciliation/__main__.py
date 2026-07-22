"""`python -m jarvis.fill_reconciliation <cmd>` — 체결 대조 CLI. 집행/주문/write 없음.

  check [--commit]   P8.1 요청 → 내부기록, 브로커 체결과 대조(현주소: 라이브 체결 없음)
  status             대조 원장 요약(이벤트 수·상태 분포)
  verify             해시체인 무결성 검증
  replay             체인 재검증(결정적)

읽기전용 — 어떤 것도 변경/집행하지 않음. 브로커 write 없음.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _internal_records() -> list:
    """P8.1 집행 요청 원장(데이터 파일)에서 내부 기대 기록 구성.

    코드 결합 회피 — sibling 패키지 import 없이 JSONL만 읽음(읽기전용 데이터 의존).
    """
    import json
    import os

    from jarvis.config import state_path
    from jarvis.fill_reconciliation.models import InternalExecutionRecord
    p = state_path("live_execution_requests.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    with open(p) as f:
        for ln in f:
            if not ln.strip():
                continue
            r = json.loads(ln)
            out.append(InternalExecutionRecord(
                order_id=r["request_id"], request_id=r["request_id"],
                expected_quantity=float(r.get("quantity", 0.0)),
                expected_price=float(r.get("limit_price") or 0.0),
                expected_side=r.get("side", ""), submitted_at=r.get("created_at", "")))
    return out


def _broker_fills() -> list:
    """라이브 브로커 체결 소스 — 현주소 없음(honest CLOSED)."""
    return []


def _cmd_check(commit: bool) -> int:
    from jarvis.fill_reconciliation.engine import FillReconciliationEngine
    now = _now()
    records = _internal_records()
    fills = _broker_fills()
    reports = FillReconciliationEngine().reconcile_batch(records, fills, now, commit=commit)
    dist: dict = {}
    for r in reports:
        dist[r.status] = dist.get(r.status, 0) + 1
    print(json.dumps({"records": len(records), "fills": len(fills),
                      "reports": len(reports), "status_distribution": dist,
                      "committed": commit,
                      "note": "대조 관측만 — 집행/주문/브로커 write 없음. 라이브 체결 소스 미구성."},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_status() -> int:
    from jarvis.fill_reconciliation.ledger import last_event, read_events
    evs = read_events()
    dist: dict = {}
    for e in evs:
        dist[e.get("status")] = dist.get(e.get("status"), 0) + 1
    print(json.dumps({"n_events": len(evs), "status_distribution": dist,
                      "last_event": last_event()},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.fill_reconciliation.verify import verify_chain
    res = verify_chain()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["ok"] else 1


def _cmd_replay() -> int:
    from jarvis.fill_reconciliation.ledger import read_events
    from jarvis.fill_reconciliation.verify import verify_chain
    chain = verify_chain()
    hashes = [e.get("report_hash") for e in read_events()]
    print(json.dumps({"chain": chain, "n": len(hashes), "report_hashes": hashes},
                     ensure_ascii=False, indent=2, default=str))
    return 0 if chain["ok"] else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.fill_reconciliation")
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
