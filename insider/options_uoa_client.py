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
import functools
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeoutError

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetStatus
from alpaca.trading.requests import GetOptionContractsRequest

_KEY = os.getenv("ALPACA_API_KEY", "")
_SECRET = os.getenv("ALPACA_SECRET_KEY", "")
_TIMEOUT = 12
# requests timeout=은 connect/read만 막고 DNS(socket.getaddrinfo)는 못 막음(파이썬 자체 제약,
# urllib3 create_connection이 getaddrinfo 이후에야 settimeout 걸음) — 2026-09-03 실서버 행에서
# 이 경로로 실측(SIGUSR1 덤프: create_connection 안 getaddrinfo에서 무한 대기). _capped()의
# requests timeout으론 못 막아 티커 단위 하드 데드라인을 별도 스레드로 감싼다.
_SCAN_TIMEOUT = 20


def _require_key() -> None:
    if not _KEY:
        raise ValueError("ALPACA_API_KEY not set in .env")


def _capped(client):
    """alpaca-py 0.43.4는 timeout 인자를 constructor/call 어디에도 안 받음(rest.py:
    self._session.request(method, url, **opts) — opts에 timeout 키 자체가 없음, 확인함).
    라이브러리 버그라 우회 불가 — 내부 requests.Session에 직접 기본 timeout 박음.
    ponytail: private _session 속성 의존, SDK 업그레이드시 재검증 필요.
    """
    client._session.request = functools.partial(client._session.request, timeout=_TIMEOUT)
    return client


def _spot_price(ticker: str) -> float | None:
    client = _capped(StockHistoricalDataClient(api_key=_KEY, secret_key=_SECRET))
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
    trading = _capped(TradingClient(api_key=_KEY, secret_key=_SECRET, paper=True))
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

    data = _capped(OptionHistoricalDataClient(api_key=_KEY, secret_key=_SECRET))
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
        # 티커마다 새 1-worker 풀 — 공유 풀이면 타임아웃으로 버린 워커가 자리 계속 차지해
        # (max_workers=1인데 그 하나가 영구 행) 다음 티커도 막힘. 버려진 워커는 스레드 leak이지만
        # 티커당 최대 1개, 하드 데드라인 있는 게 무한 대기보다 훨씬 낫다.
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            fut = pool.submit(_scan_ticker, t.upper(), max_dte, min_otm_pct, min_vol_oi_ratio, min_volume)
            try:
                out.extend(fut.result(timeout=_SCAN_TIMEOUT))
            except _FutureTimeoutError:
                continue  # 하드 데드라인 초과(DNS 행 등) — 워커는 버리고 다음 티커로
            except Exception:
                continue  # 개별 티커 실패는 건너뛰고 나머지 계속
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    out.sort(key=lambda r: r["vol_oi_ratio"], reverse=True)
    return out
