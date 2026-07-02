"""인트라데이 봉 수집 CLI (IB TWS 필요).

실행 예:
  # 스모크 테스트 (1종목, 소량)
  PYTHONPATH=. python3 research/data/pull_intraday.py --test
  # 기본 유니버스 15m 2년 (오래 걸림, 재개가능)
  PYTHONPATH=. python3 research/data/pull_intraday.py --tf 15m --years 2

⚠️ IB 페이싱 때문에 느림(요청당 ~11s). 중단해도 재실행하면 이어받음(기존 최신 ts 이후만).
TWS/Gateway가 127.0.0.1:${IB_PORT:-7497}에서 돌아야 함.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random

from ib_async import IB

from research.data.ib_downloader import download_symbol
from research.data.intraday_store import latest_ts, save_bars, quality_report

BAR_SIZE = {"1m": "1 min", "5m": "5 mins", "15m": "15 mins", "1h": "1 hour"}

LIQUID = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "AVGO", "NFLX",
    "JPM", "V", "MA", "UNH", "XOM", "HD", "COST", "WMT", "JNJ", "PG",
]
BENCH_SECTORS = ["SPY", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
DEFAULT_UNIVERSE = LIQUID + BENCH_SECTORS


async def run(symbols: list[str], tf: str, years: float, pace: float, chunk: str, resume: bool = False):
    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "7497"))
    bar_size = BAR_SIZE[tf]

    ib = IB()
    print(f"connecting IB {host}:{port} …")
    await ib.connectAsync(host, port, clientId=random.randint(200, 899), timeout=8)
    print("connected.")
    try:
        for i, sym in enumerate(symbols, 1):
            # resume(증분): 기존 최신 ts 이후만 fetch. 미지정(백필): full years 받고 dedup 병합.
            stop_ts = latest_ts(sym, tf) if resume else None
            tag = f"incremental>{stop_ts}" if stop_ts else "full backfill"
            print(f"\n[{i}/{len(symbols)}] {sym} ({tf}, {tag})")
            try:
                rows = await download_symbol(
                    ib, sym, bar_size=bar_size, duration_per_chunk=chunk,
                    years=years, stop_before_ts=stop_ts, pace_s=pace,
                )
                total = save_bars(sym, tf, rows)
                q = quality_report(sym, tf)
                print(f"  saved: +{len(rows)} → total {total} | "
                      f"{q.get('start','?')[:10]}..{q.get('end','?')[:10]} | "
                      f"dups={q.get('duplicates')} gaps={q.get('intraday_gaps')}")
            except Exception as e:
                print(f"  ERROR {sym}: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()
        print("\ndisconnected.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="15m", choices=list(BAR_SIZE))
    ap.add_argument("--years", type=float, default=2.0)
    ap.add_argument("--pace", type=float, default=11.0, help="요청 간 대기(초), IB 페이싱")
    ap.add_argument("--chunk", default="1 Y", help="요청당 duration (15m는 1 Y=~6500봉/요청)")
    ap.add_argument("--symbols", nargs="*", help="심볼 지정(미지정=기본 유니버스)")
    ap.add_argument("--resume", action="store_true", help="증분: 기존 최신 ts 이후만(백필 아님)")
    ap.add_argument("--test", action="store_true", help="스모크: AAPL만 5일")
    args = ap.parse_args()

    if args.test:
        asyncio.run(run(["AAPL"], args.tf, years=0.02, pace=args.pace, chunk="5 D"))
    else:
        syms = args.symbols or DEFAULT_UNIVERSE
        asyncio.run(run(syms, args.tf, args.years, args.pace, args.chunk, resume=args.resume))


if __name__ == "__main__":
    main()
