"""P6.4 통합 브리지 (P7.2) — LiveMarketDataProvider → MarketDataProvider.

LiveMarketDataProvider(스트리밍) → MarketDataProvider(get_price/.get) → P6.3/P6.5 valuation.
**기존 valuation 코드 무변경**(get 인터페이스 준수). flat-mark 폴백 조합 가능.
"""
from __future__ import annotations

from jarvis.market_data.models import PriceSnapshot
from jarvis.market_data.provider import MarketDataProvider


class LiveToMarketDataAdapter(MarketDataProvider):
    """스트리밍 latest() → PriceSnapshot(get_price). valuation drop-in."""
    source_name = "live_stream"

    def __init__(self, live) -> None:
        self.live = live

    def get_price(self, symbol: str, timestamp: str | None = None) -> PriceSnapshot | None:
        tick = self.live.latest(symbol)
        if tick is None:
            return None
        # no-lookahead: 요청 timestamp보다 미래 틱이면 사용 안 함
        if timestamp is not None and tick.timestamp > timestamp:
            return None
        return PriceSnapshot(symbol=tick.symbol, price=tick.price, timestamp=tick.timestamp,
                             source=tick.source, quality=tick.quality)

    def health_check(self) -> dict:
        return {"provider": "LiveToMarketDataAdapter", "source": "live_stream",
                "live": self.live.health_check()}


def live_valuation_provider(live, positions: list):
    """페이퍼 밸류에이션용 — 실시간 스트림 + 포지션 평단 flat-mark 폴백."""
    from jarvis.market_data.bridge import paper_valuation_provider
    return paper_valuation_provider(LiveToMarketDataAdapter(live), positions)
