"""`python -m jarvis.order_lifecycle <cmd>` — 생애주기 관측 CLI. 집행/주문 없음.

  status              원장 요약(주문 수·이벤트 수·상태 분포)
  verify              전 주문 해시체인 무결성 검증
  replay [order_id]   이벤트 원장에서 상태 재구성(결정적)

읽기전용 — 어떤 것도 변경/집행하지 않음.
"""
from __future__ import annotations

import json


def _cmd_status() -> int:
    from jarvis.order_lifecycle.ledger import read_events
    evs = read_events()
    orders = sorted({e.get("order_id") for e in evs})
    # 주문별 현재 상태
    cur = {}
    for e in evs:
        cur[e["order_id"]] = e["new_state"]
    dist: dict = {}
    for s in cur.values():
        dist[s] = dist.get(s, 0) + 1
    print(json.dumps({"n_orders": len(orders), "n_events": len(evs),
                      "state_distribution": dist,
                      "note": "관측 기록만 — 집행/주문 아님"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.order_lifecycle.verify import verify_all
    res = verify_all()
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0 if res["all_ok"] else 1


def _cmd_replay(order_id: str | None) -> int:
    from jarvis.order_lifecycle.ledger import read_events
    from jarvis.order_lifecycle.verify import replay_state, verify_chain
    if order_id:
        orders = [order_id]
    else:
        orders = sorted({e.get("order_id") for e in read_events()})
    out = {oid: {"state": replay_state(oid), "chain": verify_chain(oid)} for oid in orders}
    print(json.dumps({"orders": len(orders), "replay": out},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.order_lifecycle")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("verify")
    r = sub.add_parser("replay")
    r.add_argument("order_id", nargs="?", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "verify":
        return _cmd_verify()
    if args.cmd == "replay":
        return _cmd_replay(args.order_id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
