"""Price Cache (P6.4) — append-only price_cache.jsonl. 결정적·재구축 가능.

저장: symbol, price, timestamp, source. 삭제/재작성 없음. 읽기전용 데이터 캐시(권한 무관).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path
from jarvis.market_data.models import OK, PriceSnapshot
from jarvis.market_data.provider import MarketDataProvider

_CACHE = "price_cache.jsonl"


def cache_snapshot(snap: PriceSnapshot) -> None:
    p = state_path(_CACHE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps({"symbol": snap.symbol, "price": snap.price,
                            "timestamp": snap.timestamp, "source": snap.source},
                           ensure_ascii=False, default=str) + "\n")


def read_cache() -> list[dict]:
    p = state_path(_CACHE)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def latest_from_cache() -> dict:
    """symbol별 최신 캐시(append-only fold)."""
    latest: dict = {}
    for r in read_cache():
        latest[r["symbol"]] = r
    return latest


class CacheProvider(MarketDataProvider):
    """price_cache.jsonl 백드 provider(오프라인·재구축). no-lookahead."""
    source_name = "cache"

    def get_price(self, symbol: str, timestamp: str | None = None) -> PriceSnapshot | None:
        from jarvis.market_data.models import parse_ts
        rows = [r for r in read_cache() if r["symbol"] == symbol]
        if not rows:
            return None
        if timestamp is not None:
            req = parse_ts(timestamp)
            rows = [r for r in rows if (parse_ts(r["timestamp"]) or req) <= req] if req else rows
        if not rows:
            return None
        r = rows[-1]
        return PriceSnapshot(symbol=symbol, price=float(r["price"]), timestamp=r["timestamp"],
                             source=r.get("source", "cache"), quality=OK)

    def health_check(self) -> dict:
        latest = latest_from_cache()
        return {"status": "ok" if latest else "empty", "provider": "CacheProvider",
                "source": "cache", "n_symbols": len(latest), "n_rows": len(read_cache())}


def rebuild_index() -> dict:
    """캐시 → symbol별 최신 스냅샷(결정적 재구축)."""
    return {s: {"price": r["price"], "timestamp": r["timestamp"], "source": r.get("source")}
            for s, r in latest_from_cache().items()}
