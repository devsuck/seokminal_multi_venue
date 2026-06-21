# Design: KIS Daily Bar Ingestion into Nautilus ParquetDataCatalog (Sub-project 1 of 4)

## Context

This is the first of four planned sub-projects building a multi-venue Nautilus Trader
pipeline (KIS for Korean equities, Interactive Brokers for US equities). The full scope
was decomposed into:

1. **Data catalog ingestion** (this spec) — KIS daily bars for `005930.XKRX` into a
   local `ParquetDataCatalog`.
2. KIS + IB live data adapters (`DataEngine`-facing).
3. KIS + IB execution adapters (`ExecutionEngine`-facing).
4. Multi-venue strategy + backtest runner.

Each sub-project gets its own spec → plan → implementation cycle. This spec covers
only #1.

## Decisions made during brainstorming

- **Account**: real (실전) KIS account for data retrieval. Market-data endpoints are
  read-only (no orders placed), so there's no execution risk, and it avoids the
  3-month token/account expiry that paper (모의투자) accounts have — which would break
  long-running historical backfills. Paper account is reserved for sub-project 3
  (execution testing), where order-placement risk actually matters.
- **Bar type**: daily bars (일봉), via KIS's 국내주식 기간별시세(일/주/월/년) API. Chosen
  over 1-minute bars because KIS's minute-bar endpoint only supports a very limited
  recent lookback window; daily bars support long history, which is what backtesting needs.
- **Scope**: single instrument, `005930` (Samsung Electronics, XKRX), to validate the
  full pipeline end-to-end before scaling to more symbols.
- **HTTP client**: synchronous `requests`, not `httpx`/`aiohttp`. This is a one-shot
  batch ingestion script, not a live feed — no async loop is running yet, so async
  adds complexity with no benefit here. Sub-project 2 (live data adapter) will
  introduce an async client where it actually matters (persistent WebSocket /
  concurrent venue handling).

## Architecture

```
nautilus-multi-venue/
  backends/kis/
    auth.py        # OAuth2 token fetch + in-memory cache, refresh on expiry
    client.py       # KISClient: requests.Session wrapper, get_daily_price(code, start, end)
  adapters/
    data_provider.py # KIS daily-bar JSON row -> Nautilus Bar mapping; Equity Instrument builder
  data_ingestion.py  # Entry point script
  .env.example
  tests/
    test_data_provider.py
```

### `backends/kis/auth.py`

- Reads `KIS_APP_KEY`, `KIS_APP_SECRET` from environment.
- `get_access_token() -> str`: POSTs to `/oauth2/tokenP` on
  `https://openapi.koreainvestment.com:9443` (real account domain). Caches the
  token + expiry timestamp in memory; reuses until ~60s before expiry, then
  refreshes.

### `backends/kis/client.py`

- `KISClient`: holds `requests.Session`, app key/secret, and the access token from
  `auth.py`.
- `get_daily_price(code: str, start: str, end: str) -> list[dict]`: calls
  `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice`
  (`FID_INPUT_DATE_1`/`FID_INPUT_DATE_2`). KIS caps each response at 100 rows, so
  the method loops backwards in date windows until the full `[start, end]` range is
  covered, sleeping a fixed delay between calls to respect rate limits.
- On HTTP 401, retries the call once after forcing a token refresh.

### `adapters/data_provider.py`

- `build_xkrx_equity(code: str) -> Equity`: constructs a Nautilus `Equity`
  instrument for `InstrumentId.from_str(f"{code}.XKRX")`, currency `KRW`, lot size 1.
- `map_kis_daily_bar(row: dict, bar_type: BarType) -> Bar`: converts one KIS daily
  row (open/high/low/close/volume/date strings) into a Nautilus `Bar`, using `Price`
  and `Quantity` with the instrument's precision, and constructing the bar's
  timestamp from the KIS date field (midnight KST, converted to UTC nanoseconds).
- Rows with KIS's empty/holiday closing markers are skipped before mapping.

### `data_ingestion.py`

1. Load env vars (`python-dotenv`).
2. Build the `005930.XKRX` `Equity` via `build_xkrx_equity`.
3. Instantiate `KISClient`, call `get_daily_price("005930", start, end)` for a
   configurable date range (CLI args or constants for this first pass).
4. Map all rows to `Bar` objects via `map_kis_daily_bar`.
5. Open/create a `ParquetDataCatalog` at a configurable local path (default
   `./catalog`).
6. `catalog.write_data([instrument])`, then `catalog.write_data(bars)`.
7. Print a short summary (row count, date range written).

## Error handling

- 401 response → refresh token, retry once → if it fails again, raise with the KIS
  error payload surfaced.
- Rate limiting → fixed `time.sleep` between paginated calls (KIS's documented
  per-second call limit).
- Empty/holiday rows in the response → skipped, not mapped to bars.
- Missing env vars → fail fast at startup with a clear message, before any HTTP
  call is made.

## Testing

- `tests/test_data_provider.py`: unit tests for `map_kis_daily_bar` and
  `build_xkrx_equity` using a fixed sample JSON fixture (no network calls,
  no real credentials needed).
- End-to-end validation of `data_ingestion.py` is manual: run it with real KIS
  credentials in `.env`, then inspect the resulting catalog directory (e.g. via
  `ParquetDataCatalog.bars(...)`) to confirm the round trip.

## Out of scope (deferred to later sub-projects)

- IB data, KIS/IB execution adapters, strategy logic, backtest runner.
- Async/WebSocket live data feeds.
- Multiple instruments / symbol lists (will revisit once single-symbol path is
  proven).
