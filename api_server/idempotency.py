"""In-process idempotency cache for order placement.

Guards against duplicate broker submissions when a client retries a POST
after a dropped/timed-out response (the order may have already reached the
broker even though the caller never saw a reply). Keyed by (venue,
client_order_id); TTL-bound since this only needs to survive a client's
retry window, not process restarts — losing the cache on redeploy just
means a rare double-submit risk returns, not persisted corruption.
"""
from __future__ import annotations

import time

_TTL_SECONDS = 300
_MAX_ENTRIES = 1000

_cache: dict[tuple[str, str], tuple[float, dict]] = {}


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
