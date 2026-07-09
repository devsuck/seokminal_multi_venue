"""IB 연속선물(ContFuture) 봉 로더 → intraday_store(tf=1m/5m/15m).

futures_loader.py(1d 전용)의 인트라데이 버전. ICT 킬존 등은 15m 이하 필요한데
data/intraday엔 GC/ES/NQ 1d봉만 있어서 신규.

주의: CONTFUT security type은 endDateTime을 과거로 지정하는 요청 자체를 IB API가 거부함
("Setting end date/time for continuous future security type is not allowed") — 그래서
만기별 개별계약 백필처럼 커서를 걸어가며 무한정 과거로 갈 수 없음. endDateTime=""(현재)
단발요청에서 duration만 키워서 실측한 상한(MAX_DURATION, tf별): 15m="6 M", 5m="1 M",
1m="1 M" — 이 이상은 사이즈 초과로 조용히 빈 응답. 그 이상 필요하면 만기별 개별계약
(Future+expiry, get_daily_bars_future처럼 endDateTime 자유로움)을 롤 스티칭해야 하는데
이 스크립트 범위 밖.
읽기전용. TWS 필요(IB_PORT, 기본 7496).
CLI: IB_PORT=7496 PYTHONPATH=. python3 research/data/futures_intraday_loader.py --symbols GC,ES,NQ --tf 15m
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random

from ib_async import IB
from ib_async.contract import ContFuture

from research.data.ib_downloader import _to_epoch
from research.data.intraday_store import save_bars, quality_report

EXCHANGE = {"GC": "COMEX", "ES": "CME", "NQ": "CME", "MGC": "COMEX", "MES": "CME", "MNQ": "CME"}
BAR_SIZE = {"1m": "1 min", "5m": "5 mins", "15m": "15 mins"}
MAX_DURATION = {"1m": "1 M", "5m": "1 M", "15m": "6 M"}  # 실측 상한(ContFuture 단발요청)


async def fetch(ib: IB, symbol: str, exchange: str, tf: str) -> list[dict]:
    c = ContFuture(symbol, exchange)
    q = await ib.qualifyContractsAsync(c)
    if not q:
        return []
    bars = await ib.reqHistoricalDataAsync(
        c, endDateTime="", durationStr=MAX_DURATION[tf], barSizeSetting=BAR_SIZE[tf],
        whatToShow="TRADES", useRTH=False, formatDate=2, timeout=120)
    return [{"ts_utc": _to_epoch(b.date), "open": float(b.open), "high": float(b.high),
              "low": float(b.low), "close": float(b.close), "volume": float(b.volume)} for b in bars]


async def main(symbols: list[str], tf: str, pace_s: float) -> None:
    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "7496"))
    ib = IB()
    print(f"connecting IB {host}:{port} …")
    await ib.connectAsync(host, port, clientId=random.randint(200, 899), timeout=8)
    print(f"connected. 선물 {tf}봉 수집(duration={MAX_DURATION[tf]}):\n")
    try:
        for symbol in symbols:
            exchange = EXCHANGE.get(symbol)
            if not exchange:
                print(f"  {symbol:4} exchange 매핑 없음(EXCHANGE dict에 추가 필요) — skip")
                continue
            try:
                rows = await fetch(ib, symbol, exchange, tf)
                if not rows:
                    print(f"  {symbol:4} {exchange:6} qualify/데이터 실패 — skip")
                    continue
                total = save_bars(symbol, tf, rows)
                q = quality_report(symbol, tf)
                print(f"  {symbol:4} {exchange:6} +{len(rows)}→{total} {q.get('start', '?')[:10]}..{q.get('end', '?')[:10]}")
            except Exception as e:
                print(f"  {symbol:4} ERR {type(e).__name__}: {str(e)[:70]}")
            await asyncio.sleep(pace_s)
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IB ContFuture 인트라데이 봉 수집(최근, tf별 상한)")
    parser.add_argument("--symbols", default="GC,ES,NQ")
    parser.add_argument("--tf", default="15m", choices=["1m", "5m", "15m"])
    parser.add_argument("--pace", type=float, default=3.0, help="심볼 간 대기(초), pacing violation 방지")
    args = parser.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    asyncio.run(main(syms, args.tf, args.pace))
