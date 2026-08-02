"""Alpaca 옵션체인 기반 비정상거래량(UOA) 탐지.

만기 짧고 OTM 깊은 콘트랙트에 거래량/미결제약정(OI) 비율이 급등하면 정보거래
프록시로 학계·SEC가 M&A 발표 전 red flag로 실제 사용하는 패턴(Pan & Poteshman
2006 등). 시장 전체 스캔은 API 예산상 배제 — 다른 insider leg(Form4/congress)가
이미 플래그한 소수 티커만 확인하는 용도로 설계.

주의: get_option_chain 스냅샷엔 당일 누적거래량(daily_bar)이 이 SDK 버전에서
안 실려있어(모델에 필드 자체가 없음) get_option_bars(Day, start=오늘)로 별도 조회.
"""
from __future__ import annotations

import datetime as _dt
import os

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetStatus
from alpaca.trading.requests import GetOptionContractsRequest

_KEY = os.getenv("ALPACA_API_KEY", "")
_SECRET = os.getenv("ALPACA_SECRET_KEY", "")


def _require_key() -> None:
    if not _KEY:
        raise ValueError("ALPACA_API_KEY not set in .env")


def _spot_price(ticker: str) -> float | None:
    client = StockHistoricalDataClient(api_key=_KEY, secret_key=_SECRET)
    trades = client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=ticker))
    t = trades.get(ticker)
    return float(t.price) if t else None


def _scan_ticker(
    ticker: str, max_dte: int, min_otm_pct: float, min_vol_oi_ratio: float, min_volume: int,
) -> list[dict]:
    spot = _spot_price(ticker)
    if not spot:
        return []

    today = _dt.date.today()
    trading = TradingClient(api_key=_KEY, secret_key=_SECRET, paper=True)
    contracts = trading.get_option_contracts(GetOptionContractsRequest(
        underlying_symbols=[ticker],
        status=AssetStatus.ACTIVE,
        expiration_date_gte=today,
        expiration_date_lte=today + _dt.timedelta(days=max_dte),
        limit=1000,
    )).option_contracts or []

    # OTM 필터를 먼저 걸어 거래량 조회 대상(바 API 호출)을 줄인다.
    candidates = {
        c.symbol: c for c in contracts
        if c.open_interest and int(c.open_interest) > 0
        and abs(float(c.strike_price) - spot) / spot >= min_otm_pct
    }
    if not candidates:
        return []

    data = OptionHistoricalDataClient(api_key=_KEY, secret_key=_SECRET)
    bars = data.get_option_bars(OptionBarsRequest(
        symbol_or_symbols=list(candidates.keys()),
        timeframe=TimeFrame.Day,
        # 주말/휴장일 보정용 5일 버퍼 — 마지막 바(가장 최근 거래일)만 씀.
        start=_dt.datetime.combine(today - _dt.timedelta(days=5), _dt.time.min, tzinfo=_dt.timezone.utc),
    ))

    out = []
    for sym, c in candidates.items():
        # BarSet엔 제대로 된 __contains__가 없어 `sym in bars`가 항상 False임 — .data dict로 직접 조회.
        day_bars = bars.data.get(sym, [])
        vol = int(day_bars[-1].volume) if day_bars else 0
        if vol < min_volume:
            continue
        oi = int(c.open_interest)
        ratio = vol / oi
        if ratio < min_vol_oi_ratio:
            continue
        dte = (c.expiration_date - today).days
        out.append({
            "ticker": ticker,
            "contract_symbol": sym,
            "type": c.type.value,
            "strike": float(c.strike_price),
            "expiration_date": c.expiration_date.isoformat(),
            "dte": dte,
            "spot": spot,
            "moneyness_pct": round(abs(float(c.strike_price) - spot) / spot * 100, 1),
            "volume": vol,
            "open_interest": oi,
            "vol_oi_ratio": round(ratio, 2),
        })
    return out


def get_unusual_options_activity(
    tickers: list[str],
    max_dte: int = 14,
    min_otm_pct: float = 0.10,
    min_vol_oi_ratio: float = 3.0,
    min_volume: int = 50,
) -> list[dict]:
    """tickers 각각의 옵션체인을 훑어 만기짧고+OTM깊고+거래량/OI 급등 콘트랙트만 반환(비율 내림차순)."""
    _require_key()
    out: list[dict] = []
    for t in tickers:
        try:
            out.extend(_scan_ticker(t.upper(), max_dte, min_otm_pct, min_vol_oi_ratio, min_volume))
        except Exception:
            continue  # 개별 티커 실패는 건너뛰고 나머지 계속
    out.sort(key=lambda r: r["vol_oi_ratio"], reverse=True)
    return out
