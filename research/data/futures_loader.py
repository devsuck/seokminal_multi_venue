"""IB 연속선물(ContFuture) 일봉 로더 → intraday_store(tf='1d').

TSMOM 무상관 바스켓(지수·채권·원자재). 롤 스티칭 품질 체크(큰 일간점프=롤갭).
읽기전용. TWS 필요(IB_PORT, 기본 7496).
CLI: IB_PORT=7496 PYTHONPATH=. python3 research/data/futures_loader.py
"""
from __future__ import annotations

import asyncio
import os
import random

from ib_async import IB
from ib_async.contract import ContFuture

from research.data.ib_downloader import _to_epoch
from research.data.intraday_store import save_bars, quality_report

# (symbol, exchange, asset_class) — audit로 IB 구독없이 되는 것 확인된 32시장.
BASKET_FULL = [
    ("ES", "CME", "equity"), ("NQ", "CME", "equity"), ("RTY", "CME", "equity"),
    ("YM", "CBOT", "equity"), ("EMD", "CME", "equity"), ("NKD", "CME", "equity"),
    ("ZN", "CBOT", "rates"), ("ZB", "CBOT", "rates"), ("ZF", "CBOT", "rates"),
    ("ZT", "CBOT", "rates"), ("UB", "CBOT", "rates"), ("ZQ", "CBOT", "rates"),
    ("GC", "COMEX", "metals"), ("SI", "COMEX", "metals"), ("HG", "COMEX", "metals"),
    ("PL", "NYMEX", "metals"), ("PA", "NYMEX", "metals"),
    ("CL", "NYMEX", "energy"), ("NG", "NYMEX", "energy"), ("RB", "NYMEX", "energy"),
    ("HO", "NYMEX", "energy"),
    ("ZC", "CBOT", "grains"), ("ZS", "CBOT", "grains"), ("ZW", "CBOT", "grains"),
    ("ZL", "CBOT", "grains"), ("ZM", "CBOT", "grains"),
    ("KC", "NYBOT", "softs"), ("SB", "NYBOT", "softs"), ("CT", "NYBOT", "softs"),
    ("CC", "NYBOT", "softs"), ("LE", "CME", "livestock"), ("HE", "CME", "livestock"),
]
BASKET = [(s, e) for s, e, _ in BASKET_FULL]
ASSET_CLASS = {s: ac for s, e, ac in BASKET_FULL}


async def fetch(ib: IB, symbol: str, exchange: str) -> list[dict]:
    c = ContFuture(symbol, exchange)
    q = await ib.qualifyContractsAsync(c)
    if not q:
        return []
    bars = await ib.reqHistoricalDataAsync(
        c, endDateTime="", durationStr="10 Y", barSizeSetting="1 day",
        whatToShow="TRADES", useRTH=True, formatDate=2)
    return [{"ts_utc": _to_epoch(b.date), "open": float(b.open), "high": float(b.high),
             "low": float(b.low), "close": float(b.close), "volume": float(b.volume)} for b in bars]


def _roll_jumps(rows: list[dict]) -> int:
    """연속 종가 일간 |수익률|>15% = 롤갭 의심 카운트(스티칭 품질)."""
    c = [r["close"] for r in rows]
    return sum(1 for a, b in zip(c, c[1:]) if a > 0 and abs(b / a - 1) > 0.15)


async def main():
    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "7496"))
    ib = IB()
    print(f"connecting IB {host}:{port} …")
    await ib.connectAsync(host, port, clientId=random.randint(200, 899), timeout=8)
    print("connected. 선물 일봉 수집:\n")
    try:
        for sym, exch in BASKET:
            try:
                rows = await fetch(ib, sym, exch)
                if not rows:
                    print(f"  {sym:4} {exch:6} qualify/데이터 실패 — skip")
                    continue
                total = save_bars(sym, "1d", rows)
                q = quality_report(sym, "1d")
                print(f"  {sym:4} {exch:6} +{len(rows)}→{total} {q.get('start','?')[:10]}..{q.get('end','?')[:10]} "
                      f"rolljumps={_roll_jumps(rows)}")
            except Exception as e:
                print(f"  {sym:4} ERR {type(e).__name__}: {str(e)[:70]}")
            await asyncio.sleep(1.0)
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
