# Index Data Ingestion: KOSPI + SPY (Sub-project 13)

**Goal:** Ingest two benchmark instruments into the existing `ParquetDataCatalog` — the KOSPI index (Korea) and the SPY ETF (US, S&P 500 proxy) — so a later sub-project (factor/beta exposure analysis, the next slice of the platform's Quant page) has a market benchmark to compute beta against. This sub-project is pure data ingestion: no analysis logic, no new API endpoints. It follows the same KIS/IB ingestion pattern already established in sub-1 (KIS stock data) and sub-8 (IB stock data).

## Scope

In scope:
- **KIS index endpoint**: `backends/kis/client.py` gains a new method,
  `get_daily_index_price(index_code, start, end) -> list[dict]`, calling
  KIS's `inquire-daily-indexchartprice` endpoint (a different path/TR_ID
  than the existing `get_daily_price`'s `inquire-daily-itemchartprice`).
  This is a new method alongside the existing `get_daily_price` — no
  changes to that method's signature or behavior.
- **`adapters/data_provider.py` additions**:
  - `build_kospi_index() -> IndexInstrument`: a `nautilus_trader`
    `IndexInstrument` (the library's dedicated "spot index, not directly
    tradable" type — confirmed to exist in the installed `nautilus_trader`
    version) for `KOSPI.XKRX`.
  - `map_kis_index_daily_bar(row, bar_type, price_precision) -> Bar`: maps
    one `inquire-daily-indexchartprice` response row to a `Bar`, parallel
    to the existing `map_kis_daily_bar` for stock rows (different field
    names — see "KIS Index Field Names" below).
  - `build_us_equity(symbol, venue="NASDAQ")`: add an optional `venue`
    parameter (default `"NASDAQ"`, preserving every existing caller's
    behavior unchanged) so `SPY` can be built with `venue="ARCA"`
    (`SPY.ARCA`) instead of the currently-hardcoded `.NASDAQ` suffix. SPY
    is NYSE Arca-listed; tagging it `.NASDAQ` would be factually wrong
    metadata even though IB's `"SMART"` data routing (used by
    `IBClient.get_daily_bars`, unchanged in this sub-project) would still
    successfully fetch its bars regardless of the tag.
- **Two new ingestion entry points**, mirroring the existing
  one-script-per-venue convention (`data_ingestion.py` for KIS stocks,
  `data_ingestion_ib.py` for IB stocks):
  - `data_ingestion_kospi.py`: KIS index ingestion, CLI args
    `--index-code` (default `"0001"`, the KIS code for KOSPI),
    `--start`/`--end`/`--catalog-path`, same defaults convention as
    `data_ingestion.py`.
  - No new IB entry point needed — `data_ingestion_ib.py` already accepts
    `--symbol`; it gains one new optional `--venue` CLI arg (default
    `"NASDAQ"`, so existing usage for `AAPL`/`MSFT` is unchanged) to pass
    through to `build_us_equity`. Running it with `--symbol SPY --venue
    ARCA` ingests SPY correctly tagged.
- **Tests**: unit tests for `get_daily_index_price` (mocked HTTP response,
  following the existing `get_daily_price` test's mocking pattern), for
  `build_kospi_index`/`map_kis_index_daily_bar` (following the existing
  `build_xkrx_equity`/`map_kis_daily_bar` test pattern), and for
  `build_us_equity`'s new `venue` parameter (confirms default behavior
  unchanged, confirms `venue="ARCA"` produces `SPY.ARCA`).
- **Manual verification**: real ingestion runs against the live KIS and
  IB accounts (same accounts already used in sub-1/sub-8), confirming
  `KOSPI.XKRX` and `SPY.ARCA` both land in `./catalog` with non-empty bar
  data, and — critically for the *next* sub-project's needs — confirming
  their date ranges overlap with the 4 existing instruments (per sub-10's
  established lesson: KIS and IB data ingested at different times can
  have zero overlapping dates until both are re-ingested with matching
  "last N days" windows).

Out of scope (deferred to later sub-projects):
- Beta/factor-exposure calculation itself — that's the next sub-project
  (sub-14), which will consume the index data this sub-project produces.
- The Quant page frontend — sub-15, consumes sub-14's future API
  endpoint.
- Any other benchmark/index beyond KOSPI and SPY (e.g. NASDAQ-100, KOSDAQ)
  — not requested, would be trivial to add later following this same
  pattern.
- Any change to `condition_engine/`, `backtest_runner/`,
  `correlation_analysis/`, or `api_server/` — this sub-project only adds
  data, it doesn't expose or consume it anywhere else yet.

## KIS Index Field Names

KIS's `inquire-daily-indexchartprice` endpoint uses different `output2`
row field names than the stock endpoint's `inquire-daily-itemchartprice`
(which uses `stck_oprc`/`stck_hgpr`/`stck_lwpr`/`stck_clpr`/`acml_vol`).
Based on KIS's published API reference, the index endpoint's OHLCV fields
are `bstp_nmix_oprc` (open), `bstp_nmix_hgpr` (high), `bstp_nmix_lwpr`
(low), `bstp_nmix_prpr` (close/current), and `acml_vol` (volume, same name
as the stock endpoint); the date field is `stck_bsop_date` (same name as
the stock endpoint). The request uses `FID_COND_MRKT_DIV_CODE="U"` (vs
`"J"` for stocks) and `FID_INPUT_ISCD="0001"` for KOSPI.

**This project has twice already found real KIS field-name/casing
mismatches only after hitting the live API** (sub-1's lowercase
`odno`/`ODNO` casing difference between quotations and trading domains;
sub-4's same issue resurfacing for order endpoints). Treat the field
names above as the best-available starting point from documentation, not
a verified fact — the implementation task must include a real API call
against the live KIS account before the mapper is considered correct, and
must update this spec/the code together if the field names differ in
practice (mirroring how sub-1 and sub-4 each fixed this in-flight).

## IndexInstrument Fields

`build_kospi_index()` constructs:
- `instrument_id`: `KOSPI.XKRX`
- `raw_symbol`: `"0001"` (KIS's index code)
- `currency`: `KRW` (nominal — a spot index isn't denominated in a
  tradable currency the way an equity is, but `IndexInstrument` requires
  a `currency` field, and KRW is the natural choice for a Korean index,
  consistent with `build_xkrx_equity`'s choice for KRX equities)
- `price_precision`: `2` (KOSPI is quoted like `2,650.32`, two decimals —
  different from `build_xkrx_equity`'s `0` for KRW-denominated stock
  prices, since index points aren't whole-won amounts)
- `price_increment`: `Price.from_str("0.01")`
- `size_precision` / `size_increment`: `0` / `Quantity.from_int(1)`
  (placeholders — a spot index has no trade size since it's not directly
  tradable, but `IndexInstrument` requires these fields; using the same
  pattern as if it were a unit-sized instrument)

## Testing

- `tests/test_kis_client.py` (or wherever `get_daily_price`'s existing
  tests live — extend the same file): mock `requests.Session.get` to
  return a fake `inquire-daily-indexchartprice`-shaped response, assert
  `get_daily_index_price` parses/sorts/filters rows the same way
  `get_daily_price` does (the implementation should share the pagination
  logic where possible, but if duplicating a small amount of code is
  cleaner for the index case's likely-shorter response, that's
  acceptable — KOSPI doesn't need the same long lookback pagination
  stress-testing as individual stocks since this project pulls ≤1 year
  windows).
- `tests/test_data_provider.py`: `build_kospi_index()` returns the exact
  `IndexInstrument` field values listed above; `map_kis_index_daily_bar`
  correctly converts a fake `inquire-daily-indexchartprice` row into a
  `Bar`; `build_us_equity("AAPL")` (no venue arg) still returns
  `AAPL.NASDAQ` (regression check); `build_us_equity("SPY",
  venue="ARCA")` returns `SPY.ARCA`.
- Manual end-to-end: run `data_ingestion_kospi.py` against the real KIS
  account, run `data_ingestion_ib.py --symbol SPY --venue ARCA` against
  the real IB paper account, confirm both write non-empty bars to
  `./catalog`, and confirm date-range overlap with the existing 4
  instruments (re-ingest with matching "last N days" windows if the
  initial run shows zero overlap, per the sub-10 lesson).
