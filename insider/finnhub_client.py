"""Finnhub 내부자 매매 클라이언트 — SEC EDGAR 대체.

SEC가 미국 외 IP를 광범위하게 차단(403 "Undeclared Automated Tool")해서
EDGAR 직접 조회가 독일 등 해외에서 불가 — Finnhub insider-transactions로 대체.
무료 티어 포함, 데이터 원천은 동일한 Form 4.

응답 필드를 기존 edgar_client와 동일한 dict 형태로 매핑해 엔드포인트가
그대로 쓸 수 있게 한다.
"""
from __future__ import annotations

import datetime
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

_BASE = "https://finnhub.io/api/v1/stock/insider-transactions"
_TIMEOUT = 10

# recent 피드용 기본 유니버스 — Finnhub 무료 티어엔 전시장 피드가 없어
# 대형주/고활동 종목을 병렬 조회해 합침.
FEED_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD",
    "NFLX", "AVGO", "ORCL", "CRM", "JPM", "GS", "BAC", "XOM", "CVX",
    "UNH", "LLY", "PLTR", "COIN", "MSTR", "SMCI", "INTC",
]


def _api_key() -> str:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        raise ValueError("FINNHUB_API_KEY not set")
    return key


def _map_row(r: dict, symbol: str) -> dict | None:
    code = r.get("transactionCode", "")
    if code not in ("P", "S"):  # open-market buy/sell만 (EDGAR 버전과 동일 필터)
        return None
    change = r.get("change") or 0
    price = r.get("transactionPrice") or None
    shares = abs(float(change)) if change else None
    return {
        "filing_date": r.get("filingDate", ""),
        "transaction_date": r.get("transactionDate", ""),
        "reporter": (r.get("name") or "").title(),
        "ticker": symbol,
        "issuer": symbol,
        "transaction_code": code,
        "trade_type": "BUY" if code == "P" else "SELL",
        "shares": shares,
        "price_per_share": float(price) if price else None,
        "value_usd": shares * float(price) if shares and price else None,
        "shares_owned_after": float(r["share"]) if r.get("share") is not None else None,
    }


def get_insider_transactions(ticker: str, days: int = 90) -> list[dict]:
    """단일 종목 Form 4 P/S 거래 (최신순)."""
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    resp = requests.get(
        _BASE,
        params={"symbol": ticker.upper(), "from": start.isoformat(),
                "to": end.isoformat(), "token": _api_key()},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    rows = resp.json().get("data", [])
    out = [m for r in rows if (m := _map_row(r, ticker.upper()))]
    out.sort(key=lambda x: x["transaction_date"], reverse=True)
    return out


def get_recent_feed(days: int = 7, max_filings: int = 40,
                    tickers: list[str] | None = None) -> list[dict]:
    """유니버스 종목들의 최근 P/S 거래 통합 피드 (거래일 최신순)."""
    universe = tickers or FEED_UNIVERSE
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(get_insider_transactions, t, days): t for t in universe}
        for fut in as_completed(futures, timeout=30):
            try:
                results.extend(fut.result())
            except Exception:  # noqa: BLE001 — 개별 종목 실패는 피드에서 생략
                pass
    results.sort(key=lambda x: x["transaction_date"], reverse=True)
    return results[:max_filings]
