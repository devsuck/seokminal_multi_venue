"""Hyperliquid 캔들 로더 → intraday_store(tf 라벨) 재사용.

일봉(1d)은 캡 없이 ~4년. funding 전략 P&L(가격변동)용 가격 데이터.
candleSnapshot: {"type":"candleSnapshot","req":{coin,interval,startTime,endTime}} 최대 5000개.
CLI: PYTHONPATH=. python3 research/data/hl_candle_loader.py --interval 1d --years 4
"""
from __future__ import annotations

import argparse
import time

import requests

from research.data.intraday_store import save_bars, quality_report
from research.data.hl_funding_loader import LIQUID_PERPS

HL = "https://api.hyperliquid.xyz/info"
DAY_MS = 86_400_000


def _post(body: dict, retries: int = 4):
    for a in range(retries):
        try:
            r = requests.post(HL, json=body, timeout=20)
            if r.status_code == 429:
                time.sleep(2 * (a + 1)); continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if a == retries - 1:
                raise
            time.sleep(1.5 * (a + 1))
    return []


def fetch(coin: str, interval: str, years: float) -> list[dict]:
    now = int(time.time() * 1000)
    start = now - int(years * 365 * DAY_MS)
    data = _post({"type": "candleSnapshot", "req": {
        "coin": coin, "interval": interval, "startTime": start, "endTime": now}})
    return [{"ts_utc": int(c["t"] // 1000), "open": float(c["o"]), "high": float(c["h"]),
             "low": float(c["l"]), "close": float(c["c"]), "volume": float(c["v"])} for c in data]


def run(coins: list[str], interval: str, years: float, pace_s: float):
    for i, coin in enumerate(coins, 1):
        try:
            rows = fetch(coin, interval, years)
            total = save_bars(coin, interval, rows)
            q = quality_report(coin, interval)
            print(f"[{i}/{len(coins)}] {coin} {interval}: +{len(rows)} → {total} | "
                  f"{q.get('start','?')[:10]}..{q.get('end','?')[:10]}")
        except Exception as e:
            print(f"[{i}/{len(coins)}] {coin} ERROR {e}")
        time.sleep(pace_s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--years", type=float, default=4.0)
    ap.add_argument("--pace", type=float, default=0.5)
    ap.add_argument("--coins", nargs="*")
    args = ap.parse_args()
    run(args.coins or LIQUID_PERPS, args.interval, args.years, args.pace)


if __name__ == "__main__":
    main()
