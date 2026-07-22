"""Runtime Tick Cache (P7.2) — append-only live_market_ticks.jsonl. 결정적·재구축.

기록: symbol, price, timestamp, source, quality, hash. 재시작 복구용(리플레이).
"""
from __future__ import annotations

import hashlib
import json
import os

from jarvis.config import state_path
from jarvis.live_market_data.models import MarketTick, OK
from jarvis.live_market_data.provider import LiveMarketDataProvider

_CACHE = "live_market_ticks.jsonl"


def tick_hash(symbol: str, price: float, timestamp: str, source: str) -> str:
    blob = json.dumps([symbol, price, timestamp, source], sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def record_tick(tick: MarketTick) -> dict:
    row = {"symbol": tick.symbol, "price": tick.price, "timestamp": tick.timestamp,
           "source": tick.source, "quality": tick.quality,
           "hash": tick_hash(tick.symbol, tick.price, tick.timestamp, tick.source)}
    p = state_path(_CACHE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return row


def read_ticks() -> list[dict]:
    p = state_path(_CACHE)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def latest_per_symbol() -> dict:
    latest: dict = {}
    for r in read_ticks():
        latest[r["symbol"]] = r
    return latest


class CacheStreamingProvider(LiveMarketDataProvider):
    """live_market_ticks.jsonl 백드 — 재시작 복구·리플레이. no-lookahead(clock)."""
    source_name = "cache_stream"

    def __init__(self, clock: str | None = None) -> None:
        self._clock = clock
        self._subscribed: set = set()

    def subscribe(self, symbols: list[str]) -> None:
        self._subscribed |= set(symbols)

    def latest(self, symbol: str) -> MarketTick | None:
        rows = [r for r in read_ticks() if r["symbol"] == symbol
                and (self._clock is None or r["timestamp"] <= self._clock)]
        if not rows:
            return None
        r = rows[-1]
        return MarketTick(symbol=symbol, price=float(r["price"]), bid=float(r["price"]),
                          ask=float(r["price"]), volume=0.0, timestamp=r["timestamp"],
                          source=r.get("source", "cache_stream"), quality=r.get("quality", OK))

    def health_check(self) -> dict:
        latest = latest_per_symbol()
        return {"status": "ok" if latest else "empty", "provider": "CacheStreamingProvider",
                "source": "cache_stream", "connected": bool(latest), "n_symbols": len(latest),
                "n_ticks": len(read_ticks())}


def rebuild_index() -> dict:
    return {s: {"price": r["price"], "timestamp": r["timestamp"], "quality": r.get("quality")}
            for s, r in latest_per_symbol().items()}
