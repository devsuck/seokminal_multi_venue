"""`python -m jarvis.market_data <cmd>` — 읽기전용 시장데이터 CLI. 기본 무기록.

  price --symbol S [--at TS] [--csv PATH]     단일가
  snapshot --symbols a,b [--csv PATH]         다중 스냅샷
  health [--csv PATH]                         provider 상태
  verify                                      캐시 결정적 재구축
  --commit                                    스냅샷을 price_cache.jsonl에 기록
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _provider(csv_path: str | None):
    if csv_path:
        from jarvis.market_data.adapters import CSVHistoricalProvider
        return CSVHistoricalProvider(csv_path)
    from jarvis.market_data.cache import CacheProvider
    return CacheProvider()


def _maybe_cache(snap, commit: bool) -> None:
    if commit and snap is not None:
        from jarvis.market_data.cache import cache_snapshot
        cache_snapshot(snap)


def _cmd_price(symbol, at, csv_path, commit) -> int:
    prov = _provider(csv_path)
    snap = prov.get_price(symbol, at or _now())
    _maybe_cache(snap, commit)
    print(json.dumps({"symbol": symbol, "snapshot": snap.to_dict() if snap else None,
                      "note": "read-only 시장데이터 — 주문 능력 없음"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_snapshot(symbols, csv_path, commit) -> int:
    prov = _provider(csv_path)
    now = _now()
    snaps = prov.get_snapshot(symbols, now)
    for s in snaps.values():
        _maybe_cache(s, commit)
    print(json.dumps({"as_of": now, "snapshots": {k: (v.to_dict() if v else None)
                                                  for k, v in snaps.items()}},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_health(csv_path) -> int:
    print(json.dumps(_provider(csv_path).health_check(), ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.market_data.cache import latest_from_cache, rebuild_index
    a = rebuild_index()
    b = rebuild_index()
    ok = a == b
    print(json.dumps({"ok": ok, "deterministic": ok, "n_symbols": len(a),
                      "cache_rows": len(latest_from_cache())}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.market_data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("price")
    p.add_argument("--symbol", required=True)
    p.add_argument("--at", default=None)
    p.add_argument("--csv", default=None)
    p.add_argument("--commit", action="store_true")
    s = sub.add_parser("snapshot")
    s.add_argument("--symbols", required=True)
    s.add_argument("--csv", default=None)
    s.add_argument("--commit", action="store_true")
    h = sub.add_parser("health")
    h.add_argument("--csv", default=None)
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "price":
        return _cmd_price(args.symbol, args.at, args.csv, args.commit)
    if args.cmd == "snapshot":
        return _cmd_snapshot([x for x in args.symbols.split(",") if x], args.csv, args.commit)
    if args.cmd == "health":
        return _cmd_health(args.csv)
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
