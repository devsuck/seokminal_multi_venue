"""MarketDataProvider 인터페이스 (P6.4) — 읽기전용. 주문 능력 없음.

메서드: get_price(symbol, timestamp) · get_snapshot(symbols) · health_check().
P6.3 호환: get(symbol, timestamp) 별칭(valuation drop-in).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis.market_data.models import PriceSnapshot


class MarketDataProvider(ABC):
    source_name: str = "base"

    @abstractmethod
    def get_price(self, symbol: str, timestamp: str | None = None) -> PriceSnapshot | None:
        """symbol의 timestamp 이하 최신가(없으면 latest). no-lookahead. 없으면 None."""

    def get_snapshot(self, symbols: list[str], timestamp: str | None = None) -> dict:
        return {s: self.get_price(s, timestamp) for s in symbols}

    def health_check(self) -> dict:
        return {"status": "ok", "provider": type(self).__name__, "source": self.source_name}

    # ── P6.3 valuation 호환(.get) ──
    def get(self, symbol: str, timestamp: str | None = None) -> PriceSnapshot | None:
        return self.get_price(symbol, timestamp)
