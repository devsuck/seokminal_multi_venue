"""Hyperliquid 펀딩비+미결제약정(OI) 폴링 캐시. hyperliquid/client.py(REST metaAndAssetCtxs)를 소비.
청산 레벨 추정은 여기서 하지 않는다 — 원시 funding/OI만 캐시하고, 추정 계산은 프론트(lib/orderflow-data.ts)
순수함수에서 한다(실측 청산 데이터가 아님을 프론트에서 명시)."""
import asyncio
import logging
import time
from collections.abc import Callable

from hyperliquid.client import get_meta_and_ctxs

FUNDING_POLL_INTERVAL_SEC = 60.0

logger = logging.getLogger(__name__)

FetchFn = Callable[[], tuple[list[dict], list[dict]]]

_cache: dict[str, dict] = {}


def build_funding_snapshot(universe: list[dict], ctxs: list[dict], now: float) -> dict[str, dict]:
    """coin -> {coin, funding, open_interest, mark_px, prev_day_px, day_ntl_vlm, updated_at}."""
    snapshot: dict[str, dict] = {}
    for meta, ctx in zip(universe, ctxs):
        coin = meta.get("name")
        if not coin:
            continue
        try:
            snapshot[coin] = {
                "coin": coin,
                "funding": float(ctx["funding"]),
                "open_interest": float(ctx["openInterest"]),
                "mark_px": float(ctx["markPx"]),
                "prev_day_px": float(ctx["prevDayPx"]),
                "day_ntl_vlm": float(ctx["dayNtlVlm"]),
                "updated_at": now,
            }
        except (KeyError, TypeError, ValueError):
            continue
    return snapshot


def get_cached_funding(coin: str) -> dict | None:
    return _cache.get(coin.upper())


async def funding_poll_loop(fetch_fn: FetchFn = get_meta_and_ctxs) -> None:
    while True:
        try:
            universe, ctxs = await asyncio.to_thread(fetch_fn)
            _cache.clear()
            _cache.update(build_funding_snapshot(universe, ctxs, time.time()))
        except Exception:
            logger.warning("HL 펀딩/OI 폴링 실패")
        await asyncio.sleep(FUNDING_POLL_INTERVAL_SEC)
