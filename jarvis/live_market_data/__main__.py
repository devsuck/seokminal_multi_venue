"""`python -m jarvis.live_market_data <cmd>` — 읽기전용 스트리밍 CLI. 주문 능력 없음.

  status [--provider ib|kis|mock]              health/구독
  snapshot --symbols a,b [--provider] [--commit]  최신 틱(--commit=캐시 기록)
  verify                                        캐시 결정적 재구축
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _provider(name: str, now: str):
    from jarvis.live_market_data.adapters import (
        IBStreamingProvider,
        KISStreamingProvider,
        MockStreamingProvider,
        simulate_ticks,
    )
    if name == "kis":
        return KISStreamingProvider(now)
    if name == "mock":
        return MockStreamingProvider({"DEMO": simulate_ticks(100.0, 5, "2026-07-22T00:00:00Z")},
                                     clock=now)
    return IBStreamingProvider(now)


def _cmd_status(provider) -> int:
    prov = _provider(provider, _now())
    print(json.dumps({"provider": prov.source_name, "health": prov.health_check(),
                      "note": "read-only 스트리밍 — 주문 능력 없음"},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_snapshot(symbols, provider, commit) -> int:
    now = _now()
    prov = _provider(provider, now)
    prov.subscribe(symbols)
    snaps = prov.snapshot(symbols)
    if commit:
        from jarvis.live_market_data.cache import record_tick
        for t in snaps.values():
            if t is not None:
                record_tick(t)
    print(json.dumps({"as_of": now, "provider": prov.source_name,
                      "ticks": {k: (v.to_dict() if v else None) for k, v in snaps.items()}},
                     ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_verify() -> int:
    from jarvis.live_market_data.cache import latest_per_symbol, rebuild_index
    a, b = rebuild_index(), rebuild_index()
    ok = a == b
    print(json.dumps({"ok": ok, "deterministic": ok, "n_symbols": len(a),
                      "n_ticks_cached": len(latest_per_symbol())}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jarvis.live_market_data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status")
    st.add_argument("--provider", default="ib", choices=["ib", "kis", "mock"])
    sn = sub.add_parser("snapshot")
    sn.add_argument("--symbols", required=True)
    sn.add_argument("--provider", default="mock", choices=["ib", "kis", "mock"])
    sn.add_argument("--commit", action="store_true")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "status":
        return _cmd_status(args.provider)
    if args.cmd == "snapshot":
        return _cmd_snapshot([x for x in args.symbols.split(",") if x], args.provider, args.commit)
    if args.cmd == "verify":
        return _cmd_verify()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
