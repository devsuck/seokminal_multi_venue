"""Alpaca/브로커 공통 헬퍼 — alpaca_account.py(계좌/시세)와 agents.py(에이전트 틱) 양쪽이
공유해서 쓴다(특히 _fetch_intraday_bars류는 /alpaca/intraday/* 엔드포인트와 daytrade-tick
US/KR 브랜치가 동시에 호출). 다른 두 모듈은 이 모듈을 객체로 import해서
(`from api_server.routers import alpaca_shared as shared`) `shared.X(...)`처럼 호출한다 —
테스트가 `monkeypatch.setattr(shared, "_fetch_intraday_bars", ...)`로 패치할 때 두 호출부
모두에 반영되게 하려면 이름을 바인딩해 오지 않고 모듈 경유로 불러야 한다."""
from __future__ import annotations

import datetime as dt
import os
import re

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from fastapi import HTTPException
from pydantic import BaseModel

_OCC_RE = re.compile(r"^[A-Z]+(\d{6})([CP])(\d{8})$")

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
    # BarSet엔 제대로 된 __contains__/__getitem__이 없어(`sym in resp`가 항상 False) .data dict로 직접 조회.
    bars = list(resp.data.get(symbol.upper(), []))
    return [
        {"t": b.timestamp, "o": float(b.open), "h": float(b.high),
         "l": float(b.low), "c": float(b.close), "v": float(b.volume)}
        for b in bars
    ]


def _fetch_daily_closes(symbol: str, days: int = 120) -> list[float]:
    """Fetch recent daily closes for ``symbol`` (IBClient.get_daily_bars 대체)."""
    data_client = _data_client()
    now = dt.datetime.now(dt.timezone.utc)
    req = StockBarsRequest(
        symbol_or_symbols=symbol.upper(),
        timeframe=TimeFrame.Day,
        start=now - dt.timedelta(days=days),
        feed=DataFeed.IEX,  # 무료 플랜은 최근 SIP 데이터 조회 불가 — IEX 피드 사용
    )
    resp = data_client.get_stock_bars(req)
    bars = list(resp.data.get(symbol.upper(), []))
    return [float(b.close) for b in bars]


def _option_data_client() -> OptionHistoricalDataClient:
    _require_key()
    return OptionHistoricalDataClient(api_key=ALPACA_KEY, secret_key=ALPACA_SECRET)


def _fetch_option_chain(symbol: str, max_expiries: int = 6, max_dte: int = 90) -> dict[str, list[dict]]:
    """옵션체인 스냅샷(IV/그릭스 포함) → {expiry(YYYYMMDD): [{strike,right,iv,delta,bid,ask}]}.

    IBClient.get_option_chain 대체 (Alpaca get_option_chain 스냅샷 API — 그릭스/IV 포함).
    """
    today = dt.date.today()
    client = _option_data_client()
    snapshots = client.get_option_chain(OptionChainRequest(
        underlying_symbol=symbol.upper(),
        expiration_date_gte=today,
        expiration_date_lte=today + dt.timedelta(days=max_dte),
    ))
    by_expiry: dict[str, list[dict]] = {}
    for occ_symbol, snap in snapshots.items():
        m = _OCC_RE.match(occ_symbol)
        if not m:
            continue
        yymmdd, right, strike_raw = m.groups()
        expiry = "20" + yymmdd
        quote = getattr(snap, "latest_quote", None)
        greeks = getattr(snap, "greeks", None)
        by_expiry.setdefault(expiry, []).append({
            "strike": int(strike_raw) / 1000.0,
            "right": right,
            "iv": getattr(snap, "implied_volatility", None),
            "delta": getattr(greeks, "delta", None) if greeks else None,
            "bid": float(quote.bid_price) if quote and quote.bid_price else None,
            "ask": float(quote.ask_price) if quote and quote.ask_price else None,
        })
    if len(by_expiry) > max_expiries:
        kept = sorted(by_expiry)[:max_expiries]
        by_expiry = {k: by_expiry[k] for k in kept}
    return by_expiry


_IB_BAR_SIZE_TO_TIMEFRAME = {
    "1 min": TimeFrame(1, TimeFrameUnit.Minute), "2 mins": TimeFrame(2, TimeFrameUnit.Minute),
    "3 mins": TimeFrame(3, TimeFrameUnit.Minute), "5 mins": TimeFrame(5, TimeFrameUnit.Minute),
    "10 mins": TimeFrame(10, TimeFrameUnit.Minute), "15 mins": TimeFrame(15, TimeFrameUnit.Minute),
    "20 mins": TimeFrame(20, TimeFrameUnit.Minute), "30 mins": TimeFrame(30, TimeFrameUnit.Minute),
    "1 hour": TimeFrame(1, TimeFrameUnit.Hour), "2 hours": TimeFrame(2, TimeFrameUnit.Hour),
    "3 hours": TimeFrame(3, TimeFrameUnit.Hour), "4 hours": TimeFrame(4, TimeFrameUnit.Hour),
    "8 hours": TimeFrame(8, TimeFrameUnit.Hour),
    "1 day": TimeFrame.Day, "1 week": TimeFrame.Week, "1 month": TimeFrame.Month,
}

_IB_DURATION_UNIT_DAYS = {"S": 1 / 86400, "D": 1, "W": 7, "M": 30, "Y": 365}


def _parse_ib_duration_days(duration_str: str) -> float:
    """IB 'duration' 문법("1 Y", "90 D" 등) → 일수. 파싱 실패 시 365일 기본값."""
    parts = duration_str.strip().split()
    if len(parts) == 2 and parts[1][:1] in _IB_DURATION_UNIT_DAYS and parts[0].lstrip("-").isdigit():
        return int(parts[0]) * _IB_DURATION_UNIT_DAYS[parts[1][:1]]
    return 365.0


class _StockBar:
    __slots__ = ("date", "open", "high", "low", "close", "volume")

    def __init__(self, b) -> None:
        self.date = b.timestamp
        self.open, self.high, self.low, self.close, self.volume = (
            float(b.open), float(b.high), float(b.low), float(b.close), float(b.volume),
        )


def _fetch_stock_bars(symbol: str, end_date: str, duration: str, bar_size: str) -> list[_StockBar]:
    """IBClient.get_daily_bars(symbol, end_date, duration, bar_size) 대체 (주식 전용)."""
    timeframe = _IB_BAR_SIZE_TO_TIMEFRAME.get(bar_size, TimeFrame.Day)
    end = dt.datetime.now(dt.timezone.utc)
    if end_date:
        try:
            end = dt.datetime.strptime(end_date.strip()[:8], "%Y%m%d").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass
    start = end - dt.timedelta(days=_parse_ib_duration_days(duration))
    data_client = _data_client()
    req = StockBarsRequest(symbol_or_symbols=symbol.upper(), timeframe=timeframe, start=start, end=end,
                            feed=DataFeed.IEX)  # 무료 플랜은 최근 SIP 데이터 조회 불가
    resp = data_client.get_stock_bars(req)
    raw = list(resp.data.get(symbol.upper(), []))
    return [_StockBar(b) for b in raw]


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
