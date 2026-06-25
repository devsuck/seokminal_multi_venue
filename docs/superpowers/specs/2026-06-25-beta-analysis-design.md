# Factor/Beta Exposure Analysis (Sub-project 14)

**Goal:** A single function that, given an instrument and a benchmark index, queries their daily bars from the existing `ParquetDataCatalog` and computes the instrument's market beta (systematic risk exposure) relative to the benchmark. This is the second half of the platform roadmap's Phase 3 ("cross-asset/cross-company correlation & factor-exposure analysis"); correlation is sub-10, and the dashboard-backend visualization half of Phase 3 is already done in sub-11.

## Scope

In scope:
- Six instruments across two venues in `./catalog`: `005930.XKRX`, `000660.XKRX`, `KOSPI.XKRX` (KIS), `AAPL.NASDAQ`, `MSFT.NASDAQ`, `SPY.ARCA` (IB) — all ingested in sub-13, with verified date overlaps.
- A single function, `beta_for_pair(instrument_id, benchmark_id, bar_type_instrument, bar_type_benchmark, start_ns, end_ns, catalog_path) -> {beta: float, correlation: float}`, returning the instrument's beta against the benchmark (covariance of daily returns / variance of benchmark returns) and the Pearson correlation between them, computed over the date range common to both.
- Two benchmark pairings (user-facing in sub-15's Quant page):
  - KRX instruments (`005930`, `000660`) vs. `KOSPI.XKRX` (market benchmark).
  - US instruments (`AAPL`, `MSFT`) vs. `SPY.ARCA` (market benchmark).
- Reuses the same catalog-query pattern already established in sub-9/sub-10 (`ParquetDataCatalog.bars(bar_types=[...])`, filtered by `start_ns <= ts_event <= end_ns`).

Out of scope (deferred to later sub-projects):
- Multi-factor models (industry/style factors beyond market beta) — requires factor exposures not yet defined.
- Time-series stability analysis (rolling beta windows, beta persistence) — reserved for deeper quant research later.
- Any new data ingestion code — the 6 instruments above were already ingested in sub-13.

## Architecture

```
nautilus-multi-venue/
  beta_analysis/
    __init__.py
    beta.py             # beta_for_pair(...) -> {beta: float, correlation: float}
  api_server/
    main.py             # Add GET /beta endpoint
  tests/
    test_beta.py
```

### `beta_analysis/beta.py`

```python
def beta_for_pair(
    instrument_id: str,
    benchmark_id: str,
    start_ns: int,
    end_ns: int,
    catalog_path: str,
) -> dict[str, float]:
    """
    Compute beta and correlation of instrument relative to benchmark.
    
    Returns:
        {
            'instrument_id': str,
            'benchmark_id': str,
            'beta': float,              # Cov(ret_instr, ret_bench) / Var(ret_bench)
            'correlation': float,       # Pearson correlation of returns
        }
    """
```

1. Derive `bar_type_instrument` from `instrument_id` using `bar_type_for(InstrumentId.from_str(instrument_id))` (same pattern as sub-11's `/correlation` endpoint). Query `ParquetDataCatalog(catalog_path).bars(bar_types=[bar_type_instrument])`, filter to `start_ns <= ts_event <= end_ns`. Raise `ValueError` if no bars found (instrument has no data in range).
2. Derive `bar_type_benchmark` similarly. Query benchmark bars, filter by date range. Raise `ValueError` if no bars found.
3. Compute returns for both using existing `correlation_analysis.returns.compute_returns(...)`.
4. Intersect both return-`ts_event` keys into one common date set. Raise `ValueError` if fewer than 2 common dates (beta requires >= 2 points, and this error clearly distinguishes from "no data").
5. Align both return series over common dates (sorted by `ts_event`).
6. Compute:
   - `benchmark_variance = statistics.variance(benchmark_returns)`. Raise `ValueError` if variance is < 1e-10 (numerically zero; benchmark is flat). 
   - `covariance = statistics.covariance(instrument_returns, benchmark_returns)`.
   - `beta = covariance / benchmark_variance`.
   - `correlation = statistics.correlation(instrument_returns, benchmark_returns)`.
7. Return `{'instrument_id', 'benchmark_id', 'beta', 'correlation'}`.

**Why covariance/variance, not OLS regression:** mathematically equivalent for univariate beta, simpler to compute, no external dependencies, consistent with sub-10's `statistics`-only pattern.

**Why return correlation alongside beta:** the Quant page (sub-15) will display both — correlation measures *direction* of relationship (positive/negative), beta measures *magnitude* of systematic risk. Together they're more informative than beta alone.

**Why common-date intersection (not per-pair):** same reasoning as sub-10 — ensures mathematical consistency if later analytics (portfolio variance, risk decomposition) combine multiple factors.

## API Endpoint

Add to `api_server/main.py`:

```
GET /beta?instrument_id=005930.XKRX&benchmark_id=KOSPI.XKRX&start=2024-01-01&end=2024-12-31
```

Request params (all required):
- `instrument_id: str` — the asset being analyzed.
- `benchmark_id: str` — the market benchmark.
- `start: date` (ISO 8601) — start of analysis window.
- `end: date` (ISO 8601) — end of analysis window.

Response (200 OK):
```json
{
  "instrument_id": "005930.XKRX",
  "benchmark_id": "KOSPI.XKRX",
  "beta": 1.23,
  "correlation": 0.87
}
```

Error responses:
- 400 Bad Request: instrument_id/benchmark_id not found in catalog, fewer than 2 common dates, or benchmark variance near zero. All cases return a clear message identifying the issue.

**Pattern follows sub-11's `/correlation` endpoint:** date-range query, clear error messages, no data caching.

## Error Handling

- `instrument_id` or `benchmark_id` not in catalog → `ValueError` → HTTP 400 with detail message.
- No bars found for instrument/benchmark in date range → `ValueError` (name the instrument) → HTTP 400.
- Fewer than 2 common dates → `ValueError` → HTTP 400 (message: "fewer than N common dates between {instrument_id} and {benchmark_id}").
- Benchmark variance < 1e-10 → `ValueError` → HTTP 400 (message: "benchmark has near-zero variance, beta is undefined").

## Testing

- `tests/test_beta.py`: 
  - Unit test: hand-built `Bar` lists for two instruments with engineered returns, verify beta computation against known values (e.g., perfectly correlated instruments with returns scaled 2x should have beta ≈ 2.0).
  - Unit test: benchmark with zero variance, expect `ValueError`.
  - Unit test: fewer than 2 common dates, expect `ValueError`.
  - Unit test: instrument or benchmark not in catalog, expect `ValueError` (via mocking or temp catalog).
- Manual end-to-end verification: run `beta_for_pair` against real `005930`/`KOSPI` and `AAPL`/`SPY` pairs from the catalog, confirm betas are positive and in a reasonable range (e.g., 0.5–2.0 for large-cap equities), and that both betas are close to their `/correlation` coefficients (a sanity check, not an automated assertion).

## Open Questions / Risks Carried Forward

- **Rolling windows:** This sub-project computes a single beta over a fixed date range. A future quant-research phase might want rolling 60-day or 252-day betas to track beta stability over time. Deferred; the one-shot `beta_for_pair` model is sufficient for sub-15's initial Quant page.
- **Extreme beta values:** Highly volatile instruments or misaligned trading calendars (e.g., US holidays vs. Korean holidays) could produce anomalously high/low betas. The module doesn't validate or cap these; the API caller (frontend, sub-15) should apply domain knowledge (e.g., "beta > 5 is suspicious, show a warning").
- **Benchmark selection:** This sub-project assumes the user knows the correct benchmark for an instrument (KOSPI for KRX stocks, SPY for US equities). No validation or auto-mapping is performed. Fine for sub-15's domain (user selects explicitly); a future retail-friendly platform might auto-select based on instrument metadata.
