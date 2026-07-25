"""Unified Data Provider Interface (P112) — 서로 다른 API 를 **정규화**하는 얇은 추상 계층. **읽기 전용.**

**기존 벤더 클라이언트(KIS·IB·KRX·Finnhub·SEC EDGAR·OpenDART·FRED·ECOS 등)를 재사용**한다 — jarvis 는
자격증명 없이 유지(credential-free)하므로 여기서 벤더 API 를 직접 호출하지 않는다. 각 Provider 는 이미
가져온 raw 데이터를 받아 fetch()/normalize()/validate()/health_check() 로 다루고, 기존 P96-100 어댑터
(market_data_adapter·news_intelligence·earnings_intelligence·insider_flow)로 라우팅한다.

**벤더별 로직은 Provider 밖(기존 Layer A 클라이언트)에만 존재**한다. 새 provider/DB/원장 없음.
원칙(문서 §Constitution, §P112): 통합·조율만. 결정적. 거래·집행·주문 없음.
"""
from __future__ import annotations

import os

# ── P111 데이터 역량 카탈로그(감사 결과, 정적 참조 데이터) ─────────────────────────
# 각 항목: name·category·vendor·module(기존 Layer A 클라이언트)·env_key·available·consumer(소비 어댑터)
PROVIDER_CATALOG = (
    {"name": "KIS", "category": "market", "vendor": "Korea Investment & Securities",
     "module": "backends/kis/client.py", "env_key": "KIS_APP_KEY",
     "available_data": "KR equities/futures OHLCV·quote·ws", "consumer": "market_data_adapter"},
    {"name": "IB", "category": "market", "vendor": "Interactive Brokers",
     "module": "backends/ib/client.py", "env_key": "IB_HOST",
     "available_data": "US/global OHLCV·tick", "consumer": "market_data_adapter"},
    {"name": "KRX", "category": "market", "vendor": "Korea Exchange",
     "module": "krx/client.py", "env_key": "KRX_API_KEY",
     "available_data": "index/ETF/derivatives daily", "consumer": "market_data_adapter"},
    {"name": "orderflow", "category": "market", "vendor": "Binance/Bybit/OKX/Deribit/Hyperliquid",
     "module": "orderflow/*.py", "env_key": "",
     "available_data": "crypto trade/orderflow", "consumer": "market_data_adapter"},
    {"name": "yfinance", "category": "market", "vendor": "Yahoo Finance (public)",
     "module": "api_server (inline)", "env_key": "",
     "available_data": "US/KR/crypto OHLCV·earnings·news", "consumer": "market_data_adapter"},
    {"name": "Finnhub-news", "category": "news", "vendor": "Finnhub",
     "module": "api_server/main.py·graph_api.py", "env_key": "FINNHUB_API_KEY",
     "available_data": "company/market news headlines", "consumer": "news_intelligence"},
    {"name": "SEC-EDGAR", "category": "fundamental", "vendor": "SEC EDGAR (public)",
     "module": "sec_edgar/client.py", "env_key": "",
     "available_data": "XBRL company facts·financials", "consumer": "earnings_intelligence"},
    {"name": "OpenDART-fin", "category": "fundamental", "vendor": "OpenDART",
     "module": "research/data/dart_financials.py", "env_key": "OPENDART_API_KEY",
     "available_data": "KR financial statements", "consumer": "earnings_intelligence"},
    {"name": "corp_finance", "category": "fundamental", "vendor": "data.go.kr FinaStatInfo",
     "module": "corp_finance/client.py", "env_key": "DATA_GO_KR_API_KEY",
     "available_data": "KR financial statements (multi-year)", "consumer": "earnings_intelligence"},
    {"name": "yfinance-earnings", "category": "earnings", "vendor": "Yahoo Finance (public)",
     "module": "api_server/lv5_context.py", "env_key": "",
     "available_data": "earnings dates·surprise proxy", "consumer": "earnings_intelligence"},
    {"name": "Finnhub-insider", "category": "insider", "vendor": "Finnhub",
     "module": "insider/finnhub_client.py", "env_key": "FINNHUB_API_KEY",
     "available_data": "US insider transactions", "consumer": "insider_flow"},
    {"name": "SEC-Form4", "category": "insider", "vendor": "SEC EDGAR Form 4 (public)",
     "module": "insider/edgar_client.py", "env_key": "",
     "available_data": "US insider Form 4", "consumer": "insider_flow"},
    {"name": "OpenDART-insider", "category": "insider", "vendor": "OpenDART",
     "module": "insider/dart_client.py", "env_key": "OPENDART_API_KEY",
     "available_data": "KR exec stock changes·corp actions", "consumer": "insider_flow"},
    {"name": "Congress", "category": "insider", "vendor": "QuiverQuant/Senate EFD",
     "module": "insider/congress_client.py", "env_key": "",
     "available_data": "congress trading disclosures", "consumer": "insider_flow"},
    {"name": "openinsider", "category": "insider", "vendor": "openinsider.com (public)",
     "module": "research/data/openinsider.py", "env_key": "",
     "available_data": "US insider purchases", "consumer": "insider_flow"},
    {"name": "NPS-DART", "category": "ownership", "vendor": "OpenDART → NPS",
     "module": "research/data/dart_nps.py", "env_key": "OPENDART_API_KEY",
     "available_data": "KR institutional 5%+ holdings", "consumer": "insider_flow"},
    {"name": "FRED", "category": "macro", "vendor": "St. Louis Fed",
     "module": "fred/client.py", "env_key": "FRED_API_KEY",
     "available_data": "US macro series", "consumer": "event_stream"},
    {"name": "ECOS", "category": "macro", "vendor": "Bank of Korea",
     "module": "ecos/client.py", "env_key": "ECOS_API_KEY",
     "available_data": "KR macro series", "consumer": "event_stream"},
    {"name": "alt_data", "category": "alt", "vendor": "framework (no vendor)",
     "module": "jarvis/research_workflow/alt_data.py", "env_key": "",
     "available_data": "shipping/satellite/web/hiring/app/social/search", "consumer": "alt_data"},
)
# 감사에서 확인된 미연동 벤더(중복 아님, 추후 추가 안전) — 정직한 갭
MISSING_INTEGRATIONS = ("newsapi/RSS", "FMP/simfin", "tradingeconomics/worldbank/IMF",
                        "polygon/alpaca/twelvedata")


def _available(env_key: str) -> bool:
    """자격증명 유무 판정(네트워크 호출 없음). 공개 소스(env_key 없음)는 available=True."""
    return True if not env_key else bool(os.environ.get(env_key))


class Provider:
    """통합 Provider 기반 — fetch/normalize/validate/health_check. **벤더 로직은 밖(Layer A)에만.**

    fetch() 는 이미 가져온 raw 데이터를 주입받는다(의존성 주입) — jarvis 는 자격증명 없이 유지.
    실제 API 호출은 기존 Layer A 클라이언트가 담당한다.
    """
    category: str = "base"
    name: str = "base"
    vendor: str = ""
    env_key: str = ""
    consumer: str = ""

    def fetch(self, raw=None) -> list:
        """이미 가져온 raw 레코드를 주입받아 리스트로 반환(정규화 대상). 직접 벤더 호출 안 함."""
        return list(raw or [])

    def normalize(self, item: dict) -> dict:  # noqa: D401
        """벤더 raw 1건 → 정규화 dict. 하위 Provider 가 기존 어댑터로 위임."""
        raise NotImplementedError

    def validate(self, normalized: dict) -> dict:
        """정규화 결과 검증(결정적) — 필수 필드/유형. 값을 바꾸지 않는다."""
        ok = isinstance(normalized, dict) and not normalized.get("_error")
        return {"ok": bool(ok), "provider": self.name}

    def health_check(self) -> dict:
        """자격증명/구성 기반 가용성(네트워크 없음). available·configured·status."""
        avail = _available(self.env_key)
        return {"provider": self.name, "category": self.category, "vendor": self.vendor,
                "env_key": self.env_key or None, "configured": bool(not self.env_key or os.environ.get(self.env_key)),
                "available": avail, "status": "available" if avail else "not_configured",
                "consumer": self.consumer}


class MarketProvider(Provider):
    category, name, consumer = "market", "market", "market_data_adapter"

    def normalize(self, item: dict) -> dict:
        from jarvis.research_workflow.market_data_adapter import normalize as mnorm
        return mnorm(item, source=item.get("source", self.name)).to_dict()


class NewsProvider(Provider):
    category, name, consumer = "news", "news", "news_intelligence"

    def normalize(self, item: dict) -> dict:
        from jarvis.research_workflow.news_intelligence import analyze_headline
        text = item.get("text") or item.get("headline") or str(item)
        return analyze_headline(text, entity=item.get("entity", ""))


class FundamentalProvider(Provider):
    category, name, consumer = "fundamental", "fundamental", "earnings_intelligence"

    def normalize(self, item: dict) -> dict:
        from jarvis.research_workflow.earnings_intelligence import analyze_earnings
        return analyze_earnings(item)


class InsiderProvider(Provider):
    category, name, consumer = "insider", "insider", "insider_flow"

    def normalize(self, item: dict) -> dict:
        from jarvis.research_workflow.insider_flow import analyze_transaction
        return analyze_transaction(item).to_dict()


class MacroProvider(Provider):
    category, name, consumer = "macro", "macro", "event_stream"

    def normalize(self, item: dict) -> dict:
        from jarvis.research_workflow.event_stream import classify_event
        ev = dict(item or {})
        ev.setdefault("kind", "macro")
        return classify_event(ev)


# 카테고리 → Provider 클래스(정규화 라우팅)
_PROVIDER_CLASSES = {"market": MarketProvider, "news": NewsProvider,
                     "fundamental": FundamentalProvider, "earnings": FundamentalProvider,
                     "insider": InsiderProvider, "ownership": InsiderProvider, "macro": MacroProvider}


def provider_for(category: str) -> Provider:
    """카테고리 → 통합 Provider 인스턴스(정규화 라우터). 기존 어댑터로 위임."""
    cls = _PROVIDER_CLASSES.get((category or "").lower(), Provider)
    return cls()


def provider_registry() -> dict:
    """P111/P112 — 데이터 역량 카탈로그 + 각 provider 헬스(읽기전용). 새 저장소 없음."""
    entries = []
    by_category: dict = {}
    for c in PROVIDER_CATALOG:
        avail = _available(c["env_key"])
        by_category.setdefault(c["category"], []).append(c["name"])
        entries.append({**c, "available": avail,
                        "status": "available" if avail else "not_configured"})
    n_avail = sum(1 for e in entries if e["available"])
    return {"providers": entries, "count": len(entries), "available_count": n_avail,
            "by_category": {k: len(v) for k, v in by_category.items()},
            "categories": sorted(by_category),
            "missing_integrations": list(MISSING_INTEGRATIONS),
            "interface": ["fetch", "normalize", "validate", "health_check"],
            "is_advisory": True, "is_decision": False,
            "note": ("통합 provider 카탈로그(읽기전용) — 기존 벤더 클라이언트 재사용, jarvis 는 자격증명 없음. "
                     "벤더 로직은 Provider 밖에만. 새 provider/DB/원장 없음, 거래·집행 없음.")}
