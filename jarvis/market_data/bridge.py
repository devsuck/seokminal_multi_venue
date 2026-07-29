"""Paper 통합 브리지 (P6.4) — 실 시장데이터 + flat-mark 폴백.

P6.3 valuation은 provider.get(symbol, ts)만 요구 → MarketDataProvider가 drop-in.
FallbackProvider: 1차(실데이터) 결측 시 평단 flat-mark(하위호환). 주문 능력 없음.
"""
from __future__ import annotations

from jarvis.market_data.models import OK, PriceSnapshot
from jarvis.market_data.provider import MarketDataProvider


class FallbackProvider(MarketDataProvider):
    """primary(실데이터) → 결측 시 fallback_prices(평단) flat-mark."""
    source_name = "fallback"

    def __init__(self, primary: MarketDataProvider, fallback_prices: dict | None = None) -> None:
        self.primary = primary
        self.fallback = fallback_prices or {}

    def get_price(self, symbol: str, timestamp: str | None = None) -> PriceSnapshot | None:
        s = self.primary.get_price(symbol, timestamp)
        if s is not None:
            return s
        if symbol in self.fallback:
            return PriceSnapshot(symbol=symbol, price=float(self.fallback[symbol]),
                                 timestamp=timestamp or "", source="flat_mark_fallback", quality=OK)
        return None

    def health_check(self) -> dict:
        return {"status": "ok", "provider": "FallbackProvider", "source": "fallback",
                "primary": self.primary.health_check(), "n_fallback": len(self.fallback)}


def paper_valuation_provider(primary: MarketDataProvider, positions: list) -> FallbackProvider:
    """페이퍼 밸류에이션용 provider — 실데이터 우선, 결측은 포지션 평단 flat-mark."""
    fallback = {p["strategy_id"]: p["average_price"] for p in positions}
    return FallbackProvider(primary, fallback)
