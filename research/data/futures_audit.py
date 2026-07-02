"""IB 선물 데이터 게이트 audit — 일봉 히스토리컬 되나 / 엔티틀먼트 확인.

연속선물(ContFuture)로 긴 히스토리 시도. TSMOM 바스켓(지수·채권·FX·원자재).
읽기전용. TWS 필요(IB_PORT, 기본 7496 라이브).

실행: IB_PORT=7496 PYTHONPATH=. python3 research/data/futures_audit.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import random

from ib_async import IB
from ib_async.contract import ContFuture
from research.data.ib_downloader import _to_epoch

# (symbol, exchange, asset_class) — 넓은 후보. 되는 것만 골라 loader로.
BASKET = [
    # 지수
    ("ES", "CME", "equity"), ("NQ", "CME", "equity"), ("RTY", "CME", "equity"),
    ("YM", "CBOT", "equity"), ("EMD", "CME", "equity"), ("NKD", "CME", "equity"),
    # 금리/채권
    ("ZN", "CBOT", "rates"), ("ZB", "CBOT", "rates"), ("ZF", "CBOT", "rates"),
    ("ZT", "CBOT", "rates"), ("UB", "CBOT", "rates"), ("ZQ", "CBOT", "rates"),
    # 금속
    ("GC", "COMEX", "metals"), ("SI", "COMEX", "metals"), ("HG", "COMEX", "metals"),
    ("PL", "NYMEX", "metals"), ("PA", "NYMEX", "metals"),
    # 에너지
    ("CL", "NYMEX", "energy"), ("NG", "NYMEX", "energy"), ("RB", "NYMEX", "energy"),
    ("HO", "NYMEX", "energy"),
    # 곡물(CBOT)
    ("ZC", "CBOT", "grains"), ("ZS", "CBOT", "grains"), ("ZW", "CBOT", "grains"),
    ("ZL", "CBOT", "grains"), ("ZM", "CBOT", "grains"),
    # 소프트/축산(ICE/CME — 구독 필요할 수 있음)
    ("KC", "NYBOT", "softs"), ("SB", "NYBOT", "softs"), ("CT", "NYBOT", "softs"),
    ("CC", "NYBOT", "softs"), ("LE", "CME", "livestock"), ("HE", "CME", "livestock"),
]


async def probe(ib: IB, symbol: str, exchange: str):
    try:
        c = ContFuture(symbol, exchange)
        q = await ib.qualifyContractsAsync(c)
        if not q:
            return "qualify 실패(계약 없음/엔티틀먼트)"
        bars = await ib.reqHistoricalDataAsync(
            c, endDateTime="", durationStr="5 Y", barSizeSetting="1 day",
            whatToShow="TRADES", useRTH=True, formatDate=2)
        if not bars:
            return "0 bars (데이터/구독 없음)"
        s = dt.datetime.fromtimestamp(_to_epoch(bars[0].date), dt.timezone.utc).date()
        e = dt.datetime.fromtimestamp(_to_epoch(bars[-1].date), dt.timezone.utc).date()
        return f"OK {len(bars)} bars {s}..{e}"
    except Exception as e:
        return f"ERR {type(e).__name__}: {str(e)[:80]}"


async def main():
    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "7496"))
    ib = IB()
    print(f"connecting IB {host}:{port} …")
    await ib.connectAsync(host, port, clientId=random.randint(200, 899), timeout=8)
    print("connected. 선물 일봉 audit:\n")
    try:
        for sym, exch, ac in BASKET:
            res = await probe(ib, sym, exch)
            print(f"  {sym:5} {exch:6} {ac:14} {res}")
            await asyncio.sleep(1.0)
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
