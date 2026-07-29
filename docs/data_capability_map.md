# Data Capability Map (P111)

> Audit of all existing data providers in the repo, so P112–P120 **integrate, not duplicate**.
> Source of truth for the machine-readable catalog: `jarvis/research_workflow/providers.py::PROVIDER_CATALOG`.

## Architecture finding
Two layers exist. **Layer A** = real credentialed vendor clients living *outside* `jarvis/`
(`backends/`, `krx/`, `ksd/`, `fred/`, `ecos/`, `sec_edgar/`, `corp_finance/`, `insider/`,
`orderflow/`, `research/data/`, plus ad-hoc `yfinance` in `api_server/`). **Layer B** = `jarvis/`
credential-free, read-only abstractions (`market_data.MarketDataProvider` ABC, the P96–101 adapters).
The P112 provider layer is Layer B: it **reuses** Layer A clients and never re-implements vendor logic.

## Inventory — Provider · Available Data · Current Usage · Missing Integration · Recommended Consumer

| Provider | Category | Available Data | Current Usage | Recommended Consumer |
|---|---|---|---|---|
| KIS | market | KR equities/futures OHLCV·quote·ws | `backends/kis/*` (active) | market_data_adapter |
| IB | market | US/global OHLCV·tick | `backends/ib/*` (active) | market_data_adapter |
| KRX | market | index/ETF/derivatives daily | `krx/client.py` (active) | market_data_adapter |
| orderflow venues | market | crypto trade/orderflow (Binance/Bybit/OKX/Deribit/HL) | `orderflow/*` (active) | market_data_adapter |
| yfinance | market/earnings/news | US/KR/crypto OHLCV·earnings·news | `api_server` inline (active) | market_data_adapter |
| Finnhub | news·insider | company/market news, insider txns | `insider/finnhub_client.py`, `api_server` (active) | news_intelligence / insider_flow |
| SEC EDGAR | fundamental·insider | XBRL company facts, Form 4 | `sec_edgar/client.py`, `insider/edgar_client.py` (active) | earnings_intelligence / insider_flow |
| OpenDART | fundamental·insider·ownership | KR financials, exec stock changes, NPS 5%+ | `research/data/dart_*`, `insider/dart_client.py` (active) | earnings_intelligence / insider_flow |
| corp_finance (data.go.kr) | fundamental | KR financial statements | `corp_finance/client.py` (active) | earnings_intelligence |
| Congress/QuiverQuant | insider | congress trading disclosures | `insider/congress_client.py` (active) | insider_flow |
| openinsider | insider | US insider purchases | `research/data/openinsider.py` (active) | insider_flow |
| FRED | macro | US macro series | `fred/client.py` (active) | event_stream |
| ECOS | macro | KR macro series | `ecos/client.py` (active) | event_stream |
| alt_data | alt | shipping/satellite/web/hiring/app/social/search | framework only (P89) | alt_data.observe |

## Missing Integration (safe gaps — no duplicate)
`newsapi/RSS`, `FMP/simfin`, `tradingeconomics/worldbank/IMF`, `polygon/alpaca/twelvedata`.

## Duplication watch-list (do NOT add a fourth)
SEC/Form 4 exists 3×; OpenDART exists 4×; Finnhub is the de-facto US news+insider vendor; yfinance is
the ad-hoc OHLCV/earnings/news source (no wrapper). Extend `MarketDataProvider` + `jarvis/agents/datagate.py`;
do not add a new base class.

## Config
Credentials are per-client via `os.environ` (`KIS_APP_KEY`, `KRX_API_KEY`, `ECOS_API_KEY`, `FRED_API_KEY`,
`DATA_GO_KR_API_KEY`, `OPENDART_API_KEY`, `FINNHUB_API_KEY`). `jarvis/config.py` holds no keys by design.
Provider availability is derived from env-var presence — no network call, no credentials in `jarvis/`.

## Consumer
`/console/data-capability-map` → `providers.provider_registry()`.
