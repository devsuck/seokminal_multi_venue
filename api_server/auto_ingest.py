"""온디맨드 카탈로그 적재 — 요청된 종목의 일봉이 카탈로그에 없으면 yfinance로 자동 수집.

지원 venue:
  - 미국 주식:  AAPL.NASDAQ / BRK-B.NYSE / SPY.ARCA / ... → yfinance 심볼 그대로
  - 한국 주식:  005930.XKRX → 005930.KS, 035420.XKOS → 035420.KQ
                (XKRX인데 .KS에 없으면 .KQ 폴백 — 코스닥 종목을 XKRX로 넣은 경우)
  - 가상화폐:   BTC.HL → BTC-USD (프로젝트 컨벤션 ${coin}.HL)

KIS 토큰·IB TWS 없이 동작. 백테스트/차트 용도의 일봉 조회 전용이며,
이미 카탈로그에 있는 종목은 건드리지 않는다 (KIS/IB로 적재한 데이터 보존).
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
from pathlib import Path

from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import (
    bar_type_for,
    build_kosdaq_equity,
    build_us_equity,
    build_xkrx_equity,
)

_log = logging.getLogger("auto_ingest")
_LOCK = threading.Lock()  # 동시 요청이 같은 종목을 이중 적재하지 않게

KR_VENUES = {"XKRX", "XKOS"}
CRYPTO_VENUES = {"HL"}


def _yf_tickers(symbol: str, venue: str) -> list[str]:
    """instrument_id → 시도할 yfinance 티커 목록 (순서대로 폴백)."""
    if venue == "XKRX":
        return [f"{symbol}.KS", f"{symbol}.KQ"]
    if venue == "XKOS":
        return [f"{symbol}.KQ", f"{symbol}.KS"]
    if venue in CRYPTO_VENUES:
        return [f"{symbol}-USD"]
    # 미국 주식 — yfinance는 클래스 주식을 대시로 표기 (BRK.B → BRK-B)
    return [symbol.replace(".", "-")]


def _build_instrument(symbol: str, venue: str):
    if venue == "XKRX":
        return build_xkrx_equity(symbol)
    if venue == "XKOS":
        return build_kosdaq_equity(symbol)
    # 크립토(.HL)는 USD 2dp Equity로 취급 — 일봉 차트/게이트 백테스트 용도로 충분
    return build_us_equity(symbol, venue)


def _bar_dir(catalog_path: str, instrument_id: InstrumentId) -> Path:
    return Path(catalog_path) / "data" / "bar" / str(bar_type_for(instrument_id))


def has_bars(catalog_path: str, instrument_id: str) -> bool:
    try:
        iid = InstrumentId.from_str(instrument_id)
    except Exception:
        return False
    d = _bar_dir(catalog_path, iid)
    return d.exists() and any(d.glob("*.parquet"))


def ensure_bars(catalog_path: str, instrument_id: str, years: int = 3) -> dict:
    """카탈로그에 일봉 없으면 yfinance에서 최근 `years`년치 받아 적재.

    Returns: {"ingested": bool, "bars": int, "source": str|None, "error": str|None}
    """
    result = {"ingested": False, "bars": 0, "source": None, "error": None}
    try:
        iid = InstrumentId.from_str(instrument_id)
    except Exception as e:
        result["error"] = f"잘못된 instrument_id: {e}"
        return result

    with _LOCK:
        if has_bars(catalog_path, instrument_id):
            return result  # 이미 있음 — 기존 데이터 보존

        symbol, venue = str(iid.symbol), str(iid.venue)
        try:
            import yfinance as yf
        except ImportError:
            result["error"] = "yfinance 미설치"
            return result

        start = (dt.date.today() - dt.timedelta(days=365 * years)).isoformat()
        df = None
        used = None
        for ticker in _yf_tickers(symbol, venue):
            try:
                cand = yf.download(ticker, start=start, progress=False,
                                   auto_adjust=True, multi_level_index=False)
                if cand is not None and len(cand) >= 20:
                    df, used = cand, ticker
                    break
            except Exception as e:  # noqa: BLE001
                _log.warning("auto_ingest %s (%s) 실패: %s", instrument_id, ticker, e)
        if df is None:
            result["error"] = f"yfinance에서 {instrument_id} 데이터 못 찾음"
            return result

        instrument = _build_instrument(symbol, venue)
        bt = bar_type_for(instrument.id)
        prec = instrument.price_precision
        bars: list[Bar] = []
        for idx, row in df.iterrows():
            try:
                o, h, l, c = (float(row["Open"]), float(row["High"]),
                              float(row["Low"]), float(row["Close"]))
                if not all(v > 0 for v in (o, h, l, c)):
                    continue
                ts = dt_to_unix_nanos(
                    dt.datetime.combine(idx.date(), dt.time.min, tzinfo=dt.timezone.utc))
                bars.append(Bar(
                    bar_type=bt,
                    open=Price(o, prec), high=Price(h, prec),
                    low=Price(l, prec), close=Price(c, prec),
                    volume=Quantity(max(float(row.get("Volume", 0) or 0), 0), 0),
                    ts_event=ts, ts_init=ts,
                ))
            except Exception:  # noqa: BLE001
                continue
        if not bars:
            result["error"] = f"{instrument_id}: 변환 가능한 바 없음"
            return result

        catalog = ParquetDataCatalog(catalog_path)
        catalog.write_data([instrument])
        catalog.write_data(bars)
        _log.info("auto_ingest %s ← yfinance %s: %d bars", instrument_id, used, len(bars))
        result.update(ingested=True, bars=len(bars), source=used)
        return result
