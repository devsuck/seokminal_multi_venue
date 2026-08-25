"""US 내부자매수(Form4) 유니버스 확장용 15m봉 백필 — Alpaca IEX 무료피드.

기존 유니버스(27개 대형주)는 내부자가 주로 매도라 매수이벤트 희소(UNDERPOWERED 확정, 2026-07-17).
은행/산업재/통신/에너지 등 내부자매수가 상대적으로 흔한 섹터의 중형주로 확장.
15m봉 900일치를 research/data/intraday_store에 저장 → run_us_insider.py가 자동으로 픽업(글롭 스캔).
실행: PYTHONPATH=. python3 research/fetch_insider_universe_expansion.py
"""
from __future__ import annotations

import datetime as dt
import os
import time

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed
from dotenv import load_dotenv

from research.data.intraday_store import save_bars

load_dotenv()   # 알파카 키는 .env에만 있음 — api_server 밖에서 도는 스크립트라 직접 로드

DAYS = 900

# 은행/산업재/통신/에너지/제약 — 대형주보다 내부자매수 빈도 높은 섹터. 기존 유니버스(AAPL 등 27개)와 중복 없음.
UNIVERSE = [
    "WFC", "BAC", "C", "GS", "MS", "USB", "PNC", "TFC",
    "XOM", "CVX", "COP", "OXY",
    "PFE", "MRK", "ABBV", "BMY", "GILD",
    "CAT", "DE", "HON", "GE", "BA", "MMM",
    "F", "GM",
    "T", "VZ", "INTC",
    "DIS", "KO", "PEP", "MCD", "TGT", "LOW", "CVS", "UPS", "FDX",
]


def _fetch(client, symbol: str) -> int:
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=DAYS)
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                            start=start, end=end, feed=DataFeed.IEX)
    resp = client.get_stock_bars(req)
    bars = list(resp.data.get(symbol, []))
    rows = [{"ts_utc": int(b.timestamp.timestamp()), "open": float(b.open), "high": float(b.high),
             "low": float(b.low), "close": float(b.close), "volume": float(b.volume)} for b in bars]
    return save_bars(symbol, "15m", rows)


def main():
    client = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
    for sym in UNIVERSE:
        try:
            n = _fetch(client, sym)
            print(f"{sym}: {n} bars saved")
        except Exception as e:
            print(f"{sym}: FAILED — {e}")
        time.sleep(0.3)  # 무료 플랜 레이트리밋 여유


if __name__ == "__main__":
    main()
