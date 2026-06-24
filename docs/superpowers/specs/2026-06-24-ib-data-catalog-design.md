# IB Daily Bar Ingestion into Nautilus ParquetDataCatalog (Sub-project 8)

**Goal:** Mirror sub-project 1's KIS daily-bar ingestion, but for Interactive
Brokers: pull historical daily bars for a single US equity (`AAPL`) and write
them into the same local `ParquetDataCatalog` used by the KIS data, so that
both venues' historical data live in one queryable place. This is the
prerequisite for sub-project 9 (backtest automation + Sharpe/MDD reporting),
which needs a multi-venue historical data source to run against.

## Scope

In scope:
- One instrument (`AAPL`, `SMART`/`NASDAQ`, USD), one bar size (`1 day`),
  mirroring sub-1's single-symbol, single-timeframe starting scope.
- A new method on the existing `backends/ib/client.py`'s `IBClient` to fetch
  historical daily bars via `ib_async`'s `IB.reqHistoricalDataAsync`.
- A new mapping function in `adapters/data_provider.py` converting an
  `ib_async` `BarData` row into a Nautilus `Bar`.
- A new entry-point script, `data_ingestion_ib.py`, mirroring
  `data_ingestion.py`'s KIS flow, writing into the same `./catalog`
  `ParquetDataCatalog` directory as the existing KIS data.
- Connects via the existing paper-port convention (`127.0.0.1:7497`),
  consistent with every existing IB client in this repo (`IBClient`,
  `IBOrderClient`). Host/port/client_id remain constructor parameters (not
  hardcoded), so switching to a real-account connection later (Phase 4 live
  execution) is a config change, not a redesign.

Out of scope (deferred to later sub-projects):
- Multiple instruments or additional bar sizes/timeframes (will revisit once
  this single-symbol path is proven, same reasoning as sub-1).
- Backtest run orchestration and performance reporting — sub-project 9.
- Any change to `condition_engine` or `strategy_spawner` (sub-6, sub-7).
- KIS-side changes — sub-1's ingestion code and catalog data are untouched.
- A real-account (port 7496) connection — deferred until Phase 4 actually
  needs it; today's connection stays on the paper port like every other IB
  client in this repo.

## Architecture

```
nautilus-multi-venue/
  backends/ib/
    client.py          # IBClient: add get_daily_bars(...)
  adapters/
    data_provider.py    # add map_ib_daily_bar(...)
  data_ingestion_ib.py   # new entry point script
  tests/
    test_ib_client.py    # extend with get_daily_bars tests
    test_data_provider.py # extend with map_ib_daily_bar tests
```

### `backends/ib/client.py`

- `IBClient.get_daily_bars(symbol: str, end_date: str, duration: str) -> list[BarData]`:
  - Connects via the existing `connectAsync(host, port, client_id)` (same
    pattern as `stream_trades`).
  - Builds a `Stock(symbol, "SMART", "USD")` contract, qualifies it via
    `qualifyContractsAsync` (same as `stream_trades`).
  - Calls `ib.reqHistoricalDataAsync(contract, endDateTime=end_date,
    durationStr=duration, barSizeSetting="1 day", whatToShow="TRADES",
    useRTH=True)`.
  - If IB's response is empty (no permission, or a genuinely empty range),
    raises `ValueError` with the symbol/range in the message — never returns
    silently empty data without the caller being able to tell why.
  - If the requested `duration` would require IB to reject the request as
    too large for one call (IB enforces a maximum historical request size
    per bar size — for `"1 day"` bars this is on the order of a few years),
    `get_daily_bars` is not responsible for chunking on its own; the caller
    (`data_ingestion_ib.py`) is expected to request range sizes within IB's
    documented single-call limit for this first pass, matching sub-1's
    "configurable date range, single pass, scale up later" approach. (If a
    later sub-project needs multi-year backfills, chunking with a fixed
    sleep between calls — sub-1's pattern — would be added then.)

### `adapters/data_provider.py`

- `map_ib_daily_bar(row: BarData, bar_type: BarType, price_precision: int) -> Bar`:
  - `row.date` is a `datetime.date` (IB returns whole dates for daily bars,
    not timestamps); converted to midnight UTC nanoseconds via
    `dt_to_unix_nanos`, mirroring `map_kis_daily_bar`'s date handling.
  - `row.open`/`row.high`/`row.low`/`row.close` -> `Price(value,
    price_precision)`.
  - `row.volume` -> `Quantity(value, 0)` (whole shares, matching
    `map_kis_daily_bar`'s zero-precision volume).
  - `build_us_equity` (already implemented for sub-2/3) is reused unchanged
    for the `AAPL` instrument; `bar_type_for` (already implemented,
    venue-agnostic) is reused unchanged for the `BarType`.

### `data_ingestion_ib.py`

1. Build the `AAPL.NASDAQ` `Equity` via `build_us_equity("AAPL")`.
2. Instantiate `IBClient()` (default paper-port constructor args).
3. Call `get_daily_bars("AAPL", end_date, duration)` for a configurable
   range (CLI args or constants for this first pass, same as
   `data_ingestion.py`).
4. Map all rows to `Bar` objects via `map_ib_daily_bar`.
5. Open the existing `ParquetDataCatalog` at the same default `./catalog`
   path used by `data_ingestion.py`.
6. `catalog.write_data([instrument])`, then `catalog.write_data(bars)`.
7. Print a short summary (row count, date range written) — same shape as
   `data_ingestion.py`'s summary output.

## Error Handling

- Empty/no-permission historical response -> `ValueError` raised from
  `get_daily_bars` with symbol/range context, never silently swallowed.
- IB pacing limits (too-frequent historical requests) -> not a concern for
  this single-call, single-symbol scope; if a future sub-project chunks
  multiple calls, a fixed `time.sleep` between them (sub-1's pattern) would
  be added then.
- TWS/Gateway connection failure -> propagates uncaught; no retry logic (no
  token/auth layer exists for IB the way `backends/kis/auth.py` exists for
  KIS, so there's nothing analogous to KIS's "401 -> refresh -> retry once"
  to replicate).
- No required environment variables for this script (IB connection is
  host/port/client_id only, no app key/secret), so there's no "fail fast on
  missing env var" step the way `data_ingestion.py` has for KIS credentials.

## Testing

- `tests/test_data_provider.py`: unit test for `map_ib_daily_bar` using a
  fixed sample `BarData` fixture — no network, no real TWS connection.
- `tests/test_ib_client.py`: extend with a test for `get_daily_bars` using
  the existing `FakeIB` test double (same approach already used for
  `stream_trades`), verifying `connectAsync`/`qualifyContractsAsync`/
  `reqHistoricalDataAsync` are called with the expected arguments, and that
  an empty response raises `ValueError`.
- End-to-end validation of `data_ingestion_ib.py` is manual: run it against
  a real paper-TWS connection, then inspect the resulting catalog directory
  to confirm AAPL daily bars are present alongside the existing KIS data —
  mirrors sub-1's manual end-to-end verification step.

## Open Questions / Risks Carried Forward

- IB's historical-data permission requirements for daily bars are less
  strict than the tick-by-tick entitlement issue hit in sub-3 (daily bars
  with `whatToShow="TRADES"` typically work without a live real-time
  subscription), but this hasn't been verified against this account yet —
  the manual end-to-end run is where that gets confirmed. If it turns out
  daily bars are also blocked, escalate to the user rather than guessing at
  a workaround.
- Sub-project 9 (backtest automation) will need to query both venues'
  data out of the same catalog by `instrument_id`/`bar_type` — this
  sub-project doesn't build that query layer, only ensures the data is
  there in a compatible shape.
