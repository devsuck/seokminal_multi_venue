# API Inventory (P111)

> Companion to `data_capability_map.md` — the per-vendor client index with module paths and env keys.
> Purpose: prevent duplicate providers. All clients already exist; P112–120 reuse them.

## Market data
- **KIS** — `backends/kis/client.py` (REST), `backends/kis/ws_client.py` (websocket). Env `KIS_APP_KEY`/`KIS_APP_SECRET`.
- **IB** — `backends/ib/client.py` (`ib_async`). Env `IB_HOST`/`IB_PORT`.
- **KRX** — `krx/client.py::KRXClient` (index/ETF/derivatives daily). Env `KRX_API_KEY`.
- **KSD** — `ksd/client.py::KSDClient` (dividends, lending, rights).
- **orderflow** — `orderflow/{binance,bybit,okx,deribit,kis,ib,hl}_adapter.py` + `multi_venue_adapter.py`.
- **yfinance** — inline in `api_server/main.py`, `lv5_context.py`, `auto_ingest.py` (no wrapper class).
- Adapters: `adapters/data_provider.py` maps KIS/IB raw → nautilus objects.

## News
- **Finnhub** — `api_server/main.py::get_company_news`, `api_server/graph_api.py::_fetch_news_headlines`. Env `FINNHUB_API_KEY`.
- **yfinance.news** — `api_server/lv5_context.py::_fetch_news_headlines`.
- Absent: newsapi, gnews, RSS/feedparser, benzinga, marketaux, naver.

## Fundamental
- **SEC EDGAR** — `sec_edgar/client.py::SECEdgarClient` (XBRL company facts).
- **OpenDART** — `research/data/dart_financials.py`. Env `OPENDART_API_KEY`.
- **corp_finance (data.go.kr)** — `corp_finance/client.py::CorpFinanceClient`. Env `DATA_GO_KR_API_KEY`.
- Absent: FMP, simfin, quandl.

## Earnings
- No dedicated client — pulled ad-hoc via yfinance in `api_server/lv5_context.py`.

## Insider / ownership
- **Finnhub insider** — `insider/finnhub_client.py`. Env `FINNHUB_API_KEY`.
- **SEC Form 4** — `insider/edgar_client.py`.
- **OpenDART insider** — `insider/dart_client.py` (exec stock changes, corp actions).
- **Congress** — `insider/congress_client.py` (QuiverQuant/Senate EFD).
- **openinsider** — `research/data/openinsider.py`.
- **NPS holdings** — `research/data/dart_nps.py` (5%+ institutional).

## Macro
- **FRED** — `fred/client.py::FREDClient`. Env `FRED_API_KEY`.
- **ECOS (BOK)** — `ecos/client.py::ECOSClient`. Env `ECOS_API_KEY`.
- Absent: worldbank, tradingeconomics, imf.

## Provider abstractions (reuse targets)
`jarvis/market_data/provider.py::MarketDataProvider(ABC)` (get_price/health_check),
`jarvis/live_market_data/provider.py::LiveMarketDataProvider(ABC)`, `jarvis/agents/datagate.py` (data gate).

## Data quality (existing)
`jarvis/market_data/quality.py::assess_series/assess_provider` (freshness/missing/abnormal),
`jarvis/market_data/models.py` (`OK/STALE/MISSING`, `hours_between`). No module named `data_quality` existed — P118 adds one that reuses these.

## Consumer
`/console/data-capability-map` serves the machine-readable form (`providers.provider_registry()`).
