"""Deribit 옵션 미결제약정 기반 GEX(감마 익스포저) 계산 — 60초 폴링 캐시.
gamma는 기존 options/pricer.py:bs_greeks를 재사용(신규 BS 구현 안 함)."""
import asyncio
import datetime as dt
import logging
import time
from collections.abc import Awaitable, Callable

import httpx

from options.pricer import bs_greeks

DERIBIT_REST_URL = "https://www.deribit.com/api/v2"
GEX_POLL_INTERVAL_SEC = 60.0
CONTRACT_SIZE = 1.0  # Deribit BTC/ETH 옵션 1계약 = 1 코인

logger = logging.getLogger(__name__)

FetchFn = Callable[[str, dict], Awaitable[dict]]


async def _default_fetch(url: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def _parse_deribit_expiry(date_str: str) -> float:
    """Deribit 만기 표기(예: '27DEC26')를 UTC epoch seconds(만기일 08:00 UTC)로 변환."""
    d = dt.datetime.strptime(date_str, "%d%b%y").replace(
        hour=8, minute=0, second=0, tzinfo=dt.timezone.utc
    )
    return d.timestamp()


async def fetch_gex_by_strike(
    currency: str, fetch_fn: FetchFn = _default_fetch, now: float | None = None
) -> dict:
    """currency(BTC/ETH)의 만기 통합 스트라이크별 GEX를 계산한다."""
    currency = currency.upper()
    now = now if now is not None else time.time()
    body = await fetch_fn(
        f"{DERIBIT_REST_URL}/public/get_book_summary_by_currency",
        {"currency": currency, "kind": "option"},
    )
    instruments = body.get("result") or []

    if not instruments:
        return {"currency": currency, "spot": 0.0, "updated_at": now, "levels": []}

    spot = instruments[0]["underlying_price"]
    by_strike: dict[float, dict] = {}

    for inst in instruments:
        name_parts = inst["instrument_name"].split("-")  # BTC-27DEC26-100000-C
        if len(name_parts) != 4:
            continue
        try:
            strike = float(name_parts[2])
            option_type = "call" if name_parts[3] == "C" else "put"
            expiry_ts = _parse_deribit_expiry(name_parts[1])
        except (ValueError, IndexError):
            continue

        T = max((expiry_ts - now) / (365.0 * 86400.0), 1e-6)
        iv = (inst.get("mark_iv") or 0.0) / 100.0
        oi = inst.get("open_interest") or 0.0
        if iv <= 0 or oi <= 0:
            continue

        gamma = bs_greeks(spot, strike, T, 0.0, iv, option_type)["gamma"]
        gex = gamma * oi * CONTRACT_SIZE * (spot ** 2) * 0.01

        level = by_strike.setdefault(strike, {"strike": strike, "call_gex": 0.0, "put_gex": 0.0})
        if option_type == "call":
            level["call_gex"] += gex
        else:
            level["put_gex"] += gex

    levels = sorted(by_strike.values(), key=lambda lv: lv["strike"])
    for lv in levels:
        lv["net_gex"] = lv["call_gex"] - lv["put_gex"]

    return {"currency": currency, "spot": spot, "updated_at": now, "levels": levels}


_cache: dict[str, dict] = {}


def get_cached_gex(currency: str) -> dict | None:
    return _cache.get(currency.upper())


async def gex_poll_loop() -> None:
    while True:
        for currency in ("BTC", "ETH"):
            try:
                _cache[currency] = await fetch_gex_by_strike(currency)
            except Exception:
                logger.warning("GEX 폴링 실패: %s", currency)
        await asyncio.sleep(GEX_POLL_INTERVAL_SEC)
