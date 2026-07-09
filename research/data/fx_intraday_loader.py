"""IB FX 봉 로더 → intraday_store(tf=1m/5m/15m).

futures_intraday_loader.py(선물 ContFuture)의 FX 버전. EURUSD/USDJPY는 IDEALPRO FX.
XAUUSD는 Forex('XAUUSD') contract 자체가 qualify 안 됨(Error 200, no security definition)
— IB에서 금현물은 다른 contract 타입 필요, 이 스크립트 범위 밖(미지원).

15m은 endDateTime 커서로 주단위 청크 백필(과거 계속 걸어감, 156주≈3년).
1m/5m은 IB 단일요청 상한이 낮아(실측: 1m="1 M", 5m="3 M") 커서 없이 단발요청만 지원 —
Forex는 ContFuture와 달리 endDateTime 과거 지정 자체는 되지만, 사이즈 초과시 조용히
빈 응답이라 커서로 그 이상 걸어가봤자 의미 없음(1m 3M/6M, 5m 6M/1Y 전부 0봉 확인됨).
pacing: 60req/10min 한도, 기본 8초 간격.
읽기전용. TWS 필요(IB_PORT, 기본 7496).
CLI: IB_PORT=7496 PYTHONPATH=. python3 research/data/fx_intraday_loader.py --symbols EURUSD,USDJPY --tf 15m --weeks 156
     IB_PORT=7496 PYTHONPATH=. python3 research/data/fx_intraday_loader.py --symbols EURUSD,USDJPY --tf 1m
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import random

from ib_async import IB
from ib_async.contract import Forex

from research.data.ib_downloader import _to_epoch
from research.data.intraday_store import save_bars, quality_report

BAR_SIZE = {"1m": "1 min", "5m": "5 mins", "15m": "15 mins"}
SINGLE_SHOT_DURATION = {"1m": "1 M", "5m": "3 M"}  # 실측 상한 — 이 tf는 커서 없이 단발요청만


def _fmt(d: dt.datetime) -> str:
    return d.strftime("%Y%m%d %H:%M:%S")


async def fetch_chunk(ib: IB, contract: Forex, end_date: str, tf: str, duration: str) -> list[dict]:
    bars = await ib.reqHistoricalDataAsync(
        contract, endDateTime=end_date, durationStr=duration, barSizeSetting=BAR_SIZE[tf],
        whatToShow="MIDPOINT", useRTH=False, formatDate=2, timeout=90,
    )
    return [{"ts_utc": _to_epoch(b.date), "open": float(b.open), "high": float(b.high),
              "low": float(b.low), "close": float(b.close), "volume": float(b.volume)} for b in bars]


async def backfill_15m(ib: IB, pair: str, contract: Forex, weeks: int, pace_s: float) -> int:
    total = 0
    cursor = ""  # "" = now
    empty_streak = 0
    for i in range(weeks):
        try:
            rows = await fetch_chunk(ib, contract, cursor, "15m", "1 W")
        except Exception as e:
            print(f"  {pair:8} chunk {i+1}/{weeks} ERR {type(e).__name__}: {str(e)[:70]} — 다음 청크")
            await asyncio.sleep(pace_s)
            continue

        if not rows:
            empty_streak += 1
            if empty_streak >= 3:
                print(f"  {pair:8} 연속 3주 빈 응답 — 히스토리 시작점 도달로 판단, 중단")
                break
            await asyncio.sleep(pace_s)
            continue
        empty_streak = 0

        total = save_bars(pair, "15m", rows)
        earliest = min(r["ts_utc"] for r in rows)
        cursor = _fmt(dt.datetime.fromtimestamp(earliest - 1, tz=dt.timezone.utc))
        print(f"  {pair:8} chunk {i+1}/{weeks}: +{len(rows)}봉 (누적 {total}), cursor→{cursor}")
        await asyncio.sleep(pace_s)

    return total


async def backfill_single_shot(ib: IB, pair: str, contract: Forex, tf: str) -> int:
    rows = await fetch_chunk(ib, contract, "", tf, SINGLE_SHOT_DURATION[tf])
    if not rows:
        print(f"  {pair:8} {tf} 빈 응답 — skip")
        return 0
    total = save_bars(pair, tf, rows)
    print(f"  {pair:8} {tf} +{len(rows)}→{total}")
    return total


async def main(pairs: list[str], tf: str, weeks: int, pace_s: float) -> None:
    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "7496"))
    ib = IB()
    print(f"connecting IB {host}:{port} …")
    await ib.connectAsync(host, port, clientId=random.randint(200, 899), timeout=8)
    print(f"connected. FX {tf}봉 수집:\n")
    try:
        for pair in pairs:
            contract = Forex(pair)
            if not await ib.qualifyContractsAsync(contract):
                print(f"  {pair:8} qualify 실패 — skip(계정에 해당 상품 market data 권한 없을 수 있음)")
                continue
            if tf == "15m":
                await backfill_15m(ib, pair, contract, weeks, pace_s)
            else:
                await backfill_single_shot(ib, pair, contract, tf)
            q = quality_report(pair, tf)
            print(f"  {pair:8} 완료: {q.get('bars', 0)}봉 {q.get('start', '?')[:10]}..{q.get('end', '?')[:10]}\n")
            await asyncio.sleep(pace_s)
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IB FX 봉 수집")
    parser.add_argument("--symbols", default="EURUSD,USDJPY")
    parser.add_argument("--tf", default="15m", choices=["1m", "5m", "15m"])
    parser.add_argument("--weeks", type=int, default=156, help="15m 전용: 주단위 청크 수(156주≈3년)")
    parser.add_argument("--pace", type=float, default=8.0, help="요청 간 대기(초), pacing violation 방지")
    args = parser.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    asyncio.run(main(syms, args.tf, args.weeks, args.pace))
