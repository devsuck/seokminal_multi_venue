"""jarvis.market_data — Real Market Data Feed Layer (P6.4).

읽기전용 시장데이터(페이퍼 밸류에이션용). **라이브 아님·브로커 없음·주문 없음.**
MarketDataProvider(get_price/get_snapshot/health_check) + CSV/캐시 어댑터 + 품질 +
flat-mark 폴백 브리지. P6.3 valuation drop-in(.get 호환). append-only 캐시.
"""
from jarvis.market_data.adapters import CSVHistoricalProvider, PublicAPIProvider  # noqa: F401
from jarvis.market_data.bridge import FallbackProvider, paper_valuation_provider  # noqa: F401
from jarvis.market_data.cache import CacheProvider, cache_snapshot, rebuild_index  # noqa: F401
from jarvis.market_data.models import MarketDataQualityReport, OHLCVBar, PriceSnapshot  # noqa: F401
from jarvis.market_data.provider import MarketDataProvider  # noqa: F401
from jarvis.market_data.quality import assess_provider, assess_series  # noqa: F401
