"""Hyperliquid fundingHistory 로더 — 500개(≈21일)/요청 전방 페이지네이션.

API: {"type":"fundingHistory","coin","startTime","endTime"} → startTime부터 최대 500개.
전방 진행: startTime=target_start → 500개 → 다음 startTime=마지막+1h → now까지.
rate-limit(weight) 대비 요청 간 pace 대기. 재개(기존 최신 ts 이후).
읽기전용·인증 불필요.

CLI: PYTHONPATH=. python3 research/data/hl_funding_loader.py --years 2
"""
from __future__ import annotations

import argparse
import time

import requests

from research.data.funding_store import save_funding, latest_ts, quality_report

HL = "https://api.hyperliquid.xyz/info"
DAY_MS = 86_400_000
HOUR_MS = 3_600_000

# 유동성 큰 perp 서브셋 (cross-sectional·majors). 확장 가능.
LIQUID_PERPS = [
    "BTC", "ETH", "SOL", "AVAX", "BNB", "ARB", "OP", "LINK", "LTC", "DOGE",
    "SUI", "INJ", "ATOM", "DYDX", "APT", "MATIC", "NEAR", "TIA", "SEI", "ORDI",
    "WLD", "PEPE", "kPEPE", "CRV", "AAVE",
]


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


def fetch_coin(coin: str, years: float, stop_before_ts: int | None, pace_s: float, log=print) -> list[dict]:
    now = int(time.time() * 1000)
    start = now - int(years * 365 * DAY_MS)
    if stop_before_ts:  # 재개: 기존 최신 이후만
        start = max(start, (stop_before_ts + 1) * 1000)
    rows: list[dict] = []
    last_seen = None
    for _ in range(200):
        data = _post({"type": "fundingHistory", "coin": coin, "startTime": start, "endTime": now})
        if not data:
            break
        for d in data:
            rows.append({"funding_time": int(d["time"] // 1000),
                         "funding_rate": float(d["fundingRate"]),
                         "premium": float(d.get("premium", 0) or 0)})
        newest = data[-1]["time"]
        if last_seen is not None and newest <= last_seen:
            break  # 전방 진행 없음
        last_seen = newest
        if newest >= now - HOUR_MS or len(data) < 500:
            break  # 현재 도달 or 마지막 페이지
        start = newest + HOUR_MS
        time.sleep(pace_s)
    log(f"  [{coin}] +{len(rows)} funding records")
    return rows


def run(coins: list[str], years: float, pace_s: float, resume: bool):
    for i, coin in enumerate(coins, 1):
        stop = latest_ts(coin) if resume else None
        print(f"[{i}/{len(coins)}] {coin} ({'resume' if stop else 'full'})")
        try:
            rows = fetch_coin(coin, years, stop, pace_s)
            total = save_funding(coin, rows)
            q = quality_report(coin)
            print(f"  saved total {total} | {q.get('start','?')[:10]}..{q.get('end','?')[:10]} "
                  f"dups={q.get('duplicates')} gaps={q.get('gaps_gt_1h')} cov={q.get('coverage_days')}d")
        except Exception as e:
            print(f"  ERROR {coin}: {e}")
        time.sleep(pace_s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=2.0)
    ap.add_argument("--pace", type=float, default=0.8, help="요청 간 대기(초), HL weight 한도")
    ap.add_argument("--coins", nargs="*")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    coins = args.coins or LIQUID_PERPS
    run(coins, args.years, args.pace, args.resume)


if __name__ == "__main__":
    main()
