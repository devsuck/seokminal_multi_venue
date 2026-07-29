"""Alpaca/브로커 공통 헬퍼 — alpaca_account.py(계좌/시세)와 agents.py(에이전트 틱) 양쪽이
공유해서 쓴다(특히 _fetch_intraday_bars류는 /alpaca/intraday/* 엔드포인트와 daytrade-tick
US/KR 브랜치가 동시에 호출). 다른 두 모듈은 이 모듈을 객체로 import해서
(`from api_server.routers import alpaca_shared as shared`) `shared.X(...)`처럼 호출한다 —
테스트가 `monkeypatch.setattr(shared, "_fetch_intraday_bars", ...)`로 패치할 때 두 호출부
모두에 반영되게 하려면 이름을 바인딩해 오지 않고 모듈 경유로 불러야 한다."""
from __future__ import annotations

import datetime as dt
import os

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from fastapi import HTTPException
from pydantic import BaseModel

ALPACA_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")


def _require_key() -> None:
    if not ALPACA_KEY:
        raise HTTPException(status_code=503, detail="ALPACA_API_KEY not set in .env")


def _trading_client(paper: bool = ALPACA_PAPER) -> TradingClient:
    _require_key()
    return TradingClient(api_key=ALPACA_KEY, secret_key=ALPACA_SECRET, paper=paper)


def _data_client() -> StockHistoricalDataClient:
    _require_key()
    return StockHistoricalDataClient(api_key=ALPACA_KEY, secret_key=ALPACA_SECRET)


def _fmt_order(o) -> dict:
    return {
        "id": str(o.id),
        "symbol": o.symbol,
        "side": o.side.value,
        "qty": float(o.qty) if o.qty is not None else 0.0,
        "filled_qty": float(o.filled_qty) if o.filled_qty is not None else 0.0,
        "status": o.status.value,
        "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price is not None else None,
        "created_at": o.created_at.isoformat() if o.created_at else "",
    }


# ── Technical Indicators ──────────────────────────────────────────────────────

def calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calc_ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    emas = [values[0]]
    for v in values[1:]:
        emas.append(v * k + emas[-1] * (1 - k))
    return emas


def calc_macd(closes: list[float]) -> tuple[float, float, float]:
    """Returns (macd, signal, histogram)."""
    if len(closes) < 26:
        return 0.0, 0.0, 0.0
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
    signal_line = calc_ema(macd_line, 9) if len(macd_line) >= 9 else [macd_line[-1]]
    macd_val = round(macd_line[-1], 4)
    signal_val = round(signal_line[-1], 4)
    return macd_val, signal_val, round(macd_val - signal_val, 4)


class OrderRequest(BaseModel):
    symbol: str
    side: str           # "buy" | "sell"
    qty: float
    type: str = "market"        # "market" | "limit"
    limit_price: float | None = None
    paper: bool = True


def _fetch_intraday_bars(symbol: str, days: int = 2) -> list[dict]:
    """Fetch recent 5-min bars for ``symbol`` as intraday_score-shaped dicts."""
    data_client = _data_client()
    now = dt.datetime.now(dt.timezone.utc)
    req = StockBarsRequest(
        symbol_or_symbols=symbol.upper(),
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=now - dt.timedelta(days=days),
        limit=200,
    )
    resp = data_client.get_stock_bars(req)
    bars = list(resp[symbol.upper()]) if symbol.upper() in resp else []
    return [
        {"t": b.timestamp, "o": float(b.open), "h": float(b.high),
         "l": float(b.low), "c": float(b.close), "v": float(b.volume)}
        for b in bars
    ]


def _fetch_kr_intraday_bars(symbol: str) -> list[dict]:
    """KR 5-min bars via yfinance (.KS/.KQ) → intraday_score bar dicts."""
    import yfinance as yf
    h = yf.Ticker(symbol).history(period="5d", interval="5m")
    out = []
    for ts, row in h.iterrows():
        out.append({
            "t": ts.to_pydatetime(), "o": float(row["Open"]), "h": float(row["High"]),
            "l": float(row["Low"]), "c": float(row["Close"]), "v": float(row["Volume"]),
        })
    return out
