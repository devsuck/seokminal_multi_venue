"""Hyperliquid 데이터 게이트 audit — 전략 만들기 전에 뭐가 가능한지부터.

확인: candleSnapshot 실제 깊이 / fundingHistory 길이 / perp universe / OI·funding /
spot 대응(델타중립 가능 자산) / 수수료 가정. 읽기전용(주문 아님, 인증 불필요).

실행: PYTHONPATH=. python3 research/data/hl_audit.py
"""
from __future__ import annotations

import datetime as dt
import time

import requests

HL = "https://api.hyperliquid.xyz/info"
DAY_MS = 86_400_000

# HL perps 수수료(기본 티어): taker 0.045% = 4.5bps, maker 0.015% = 1.5bps.
FEES = {"taker_bps": 4.5, "maker_bps": 1.5}


def _post(body: dict):
    r = requests.post(HL, json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def _ts(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def audit_universe():
    meta = _post({"type": "meta"})
    uni = meta.get("universe", [])
    print(f"\n[perp universe] {len(uni)} coins")
    print("  sample:", ", ".join(u["name"] for u in uni[:20]))
    return [u["name"] for u in uni]


def audit_ctxs():
    meta, ctxs = _post({"type": "metaAndAssetCtxs"})
    names = [u["name"] for u in meta["universe"]]
    print(f"\n[asset ctxs] funding/OI 현재값 (상위 8)")
    rows = []
    for n, c in zip(names, ctxs):
        try:
            rows.append((n, float(c.get("funding", 0)) * 100, float(c.get("openInterest", 0)),
                         float(c.get("markPx", 0))))
        except (TypeError, ValueError):
            pass
    for n, f, oi, mk in rows[:8]:
        print(f"  {n:8} funding(1h)={f:+.5f}%  OI={oi:,.0f}  mark={mk}")
    return rows


def audit_candle_depth(coin="BTC"):
    print(f"\n[candleSnapshot 깊이] {coin}")
    now = int(time.time() * 1000)
    for interval, back_days in [("15m", 400), ("1h", 700), ("1d", 1500)]:
        try:
            data = _post({"type": "candleSnapshot", "req": {
                "coin": coin, "interval": interval,
                "startTime": now - back_days * DAY_MS, "endTime": now}})
            if data:
                span = f"{_ts(data[0]['t'])}..{_ts(data[-1]['t'])}"
                days = (data[-1]['t'] - data[0]['t']) / DAY_MS
                print(f"  {interval:4} 요청 {back_days}d → {len(data)}개  {span}  (~{days:.0f}일)")
            else:
                print(f"  {interval:4} → 0개")
        except Exception as e:
            print(f"  {interval:4} ERR {e}")
        time.sleep(0.3)


def audit_funding_history(coin="BTC"):
    print(f"\n[fundingHistory 깊이] {coin}")
    now = int(time.time() * 1000)
    for back_days in [400, 800]:
        try:
            data = _post({"type": "fundingHistory", "coin": coin,
                          "startTime": now - back_days * DAY_MS, "endTime": now})
            if data:
                span = f"{_ts(data[0]['time'])}..{_ts(data[-1]['time'])}"
                days = (data[-1]['time'] - data[0]['time']) / DAY_MS
                print(f"  요청 {back_days}d → {len(data)}개  {span}  (~{days:.0f}일)")
            else:
                print(f"  요청 {back_days}d → 0개")
        except Exception as e:
            print(f"  ERR {e}")
        time.sleep(0.3)


def audit_spot():
    print(f"\n[spot 대응] 델타중립(long spot + short perp) 가능 자산")
    try:
        sm = _post({"type": "spotMeta"})
        toks = [t["name"] for t in sm.get("tokens", [])]
        print(f"  spot 토큰 {len(toks)}개: {', '.join(toks[:25])}")
        print("  → 진짜 델타중립은 spot 있는 자산만(BTC/ETH 등). 나머지는 perp-only funding signal")
    except Exception as e:
        print(f"  ERR {e}")


def main():
    print("=" * 74)
    print("HYPERLIQUID DATA AUDIT — 전략 전에 데이터 게이트")
    print("=" * 74)
    audit_universe()
    audit_ctxs()
    audit_candle_depth("BTC")
    audit_funding_history("BTC")
    audit_funding_history("ETH")
    audit_spot()
    print(f"\n[수수료 가정] perps taker {FEES['taker_bps']}bps / maker {FEES['maker_bps']}bps "
          f"(왕복 taker ~{FEES['taker_bps']*2}bps). 알트 slippage 별도·보수적으로")


if __name__ == "__main__":
    main()
