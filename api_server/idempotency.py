"""In-process idempotency cache for order placement.

Guards against duplicate broker submissions when a client retries a POST
after a dropped/timed-out response (the order may have already reached the
broker even though the caller never saw a reply). Keyed by (venue,
client_order_id); TTL-bound since this only needs to survive a client's
retry window, not process restarts — losing the cache on redeploy just
means a rare double-submit risk returns, not persisted corruption.
"""
from __future__ import annotations

import asyncio
import threading
import time

_TTL_SECONDS = 300
_MAX_ENTRIES = 1000

_cache: dict[tuple[str, str], tuple[float, dict]] = {}

_sync_locks: dict[str, threading.Lock] = {}
_async_locks: dict[str, asyncio.Lock] = {}


def lock(venue: str) -> threading.Lock:
    """venue별 전역 락 — sync 주문 엔드포인트(KR)의 get_cached→브로커 호출→store
    구간을 직렬화해 동시 요청의 이중 제출을 막음.
    ponytail: venue 전체 직렬화, 처리량 문제되면 client_order_id별 락으로 세분화."""
    return _sync_locks.setdefault(venue, threading.Lock())


def async_lock(venue: str) -> asyncio.Lock:
    """lock()과 동일 목적, async 주문 엔드포인트(US/US_OPTIONS)용."""
    return _async_locks.setdefault(venue, asyncio.Lock())


def get_cached(venue: str, client_order_id: str | None) -> dict | None:
    """Return the previously-submitted response for this key, or None (no
    client_order_id given, or none on record / expired)."""
    if not client_order_id:
        return None
    _evict_expired()
    entry = _cache.get((venue, client_order_id))
    return entry[1] if entry else None


def store(venue: str, client_order_id: str | None, response: dict) -> None:
    """Record a successful submission's response so a retry with the same
    client_order_id short-circuits instead of re-submitting to the broker."""
    if not client_order_id:
        return
    _evict_expired()
    if len(_cache) >= _MAX_ENTRIES:
        oldest_key = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest_key, None)
    _cache[(venue, client_order_id)] = (time.monotonic(), response)


def _evict_expired() -> None:
    cutoff = time.monotonic() - _TTL_SECONDS
    expired = [k for k, (ts, _) in _cache.items() if ts < cutoff]
    for k in expired:
        _cache.pop(k, None)
