# Cross-Asset Correlation Analysis (Sub-project 10)

**Goal:** A single function that, given a list of instruments and a date
range, queries their daily bars from the existing `ParquetDataCatalog`
(spanning both KIS and IB venues) and returns a pairwise Pearson
correlation matrix of daily returns. This is the first half of the
platform roadmap's Phase 3 ("cross-asset/cross-company correlation &
factor-exposure analysis"); factor-exposure (e.g. market beta) is
explicitly deferred to a later sub-project, and the dashboard-backend half
of Phase 3 is its own separate sub-project.

## Scope

In scope:
- Four instruments across two venues: `005930.XKRX`, `000660.XKRX` (KIS),
  `AAPL.NASDAQ`, `MSFT.NASDAQ` (IB) — all four already ingested into
  `./catalog` with overlapping date ranges (see "Data Refresh" below).
- A single function, `corr_matrix(instrument_ids, bar_type_strs, start_ns,
  end_ns, catalog_path) -> dict[tuple[str, str], float]`, returning every
  pairwise Pearson correlation (including each instrument against
  itself, which is always `1.0`) computed over the date range common to
  **all** requested instruments.
- Reuses the same catalog-query pattern already established in sub-9's
  `run_backtest` (`ParquetDataCatalog.bars(bar_types=[...])`, filtered in
  Python by `start_ns <= ts_event <= end_ns`).

Out of scope (deferred to later sub-projects):
- Factor exposure (market beta, sector/style factors) — needs a benchmark
  index instrument that isn't in this sub-project's scope.
- The dashboard-backend half of Phase 3 (time-series/alt-data
  visualization groundwork) — a separate sub-project.
- Any new data ingestion code — the 4 instruments above were ingested
  using the existing, unmodified `data_ingestion.py`/`data_ingestion_ib.py`
  CLI scripts from sub-1/sub-8 with different `--code`/`--symbol` args; no
  ingestion code changes were needed or made.
- More than 4 instruments, or any portfolio-level statistics (variance,
  risk contribution) beyond the pairwise correlation matrix itself.

## Data Refresh (done before this spec, not part of the implementation plan)

Before this sub-project could be designed, a real blocker was found and
fixed: sub-1's original KIS `005930` data (ingested months earlier in this
project's timeline) covered `2024-06-03` to `2024-06-28`, while sub-8's IB
`AAPL` data covers `2025-06-25` to `2026-06-23` — **zero overlapping
dates**, making any cross-venue correlation impossible. Fixed by re-running
the existing ingestion scripts with their current default date range
(`--code`/`--symbol` only, no other args — both scripts already default to
"last 365 days from today"):
- `data_ingestion.py --code 005930` (refreshed/appended current dates)
- `data_ingestion.py --code 000660` (new instrument)
- `data_ingestion_ib.py --symbol MSFT` (new instrument)

Confirmed after refresh: `005930` and `AAPL` now share 237 common trading
dates. This sub-project's implementation plan assumes this data already
exists in `./catalog` — it does not re-ingest anything.

## Architecture

```
nautilus-multi-venue/
  correlation_analysis/
    __init__.py
    returns.py        # compute_returns(bars) -> dict[int, float]
    correlation.py      # corr_matrix(...) -> dict[tuple[str, str], float]
  tests/
    test_returns.py
    test_correlation.py
```

### `correlation_analysis/returns.py`

```python
def compute_returns(bars: list[Bar]) -> dict[int, float]:
    """Daily close-to-close pct returns, keyed by ts_event (ns)."""
```

- Input `bars` must already be sorted ascending by `ts_event` (the
  catalog's own `bars()` query returns them sorted, consistent with every
  prior sub-project's assumption about catalog output ordering).
- Returns `{bar[i].ts_event: (bar[i].close / bar[i-1].close) - 1.0 for i in 1..len(bars)-1}`
  — the first bar in the input has no prior close, so it contributes no
  entry (a series of `N` bars produces `N-1` returns).
- Keyed by `ts_event` (nanoseconds), not a converted `datetime.date` —
  both `map_kis_daily_bar` (sub-1) and `map_ib_daily_bar` (sub-8) already
  normalize daily bars to midnight-UTC timestamps for their trading day,
  so two bars from different venues on the "same trading day" carry the
  *same* `ts_event` integer and compare equal directly, with no timezone
  conversion needed in this module.

### `correlation_analysis/correlation.py`

```python
def corr_matrix(
    instrument_ids: list[str],
    bar_type_strs: list[str],
    start_ns: int,
    end_ns: int,
    catalog_path: str,
) -> dict[tuple[str, str], float]:
    ...
```

1. Require `len(instrument_ids) >= 2` (and `len(instrument_ids) ==
   len(bar_type_strs)`, one bar type per instrument) — else `ValueError`.
2. For each `(instrument_id, bar_type_str)` pair: query
   `ParquetDataCatalog(catalog_path).bars(bar_types=[bar_type_str])`,
   filter to `start_ns <= ts_event <= end_ns` (same pattern as sub-9's
   `run_backtest`), raise `ValueError` naming the instrument if empty, then
   `compute_returns(...)`.
3. Intersect all instruments' return-`ts_event` keys into one common date
   set. Raise `ValueError` if this intersection has fewer than 2 dates
   (not enough data points for `statistics.correlation`, and a clearer
   message than the stdlib's own error in this case).
4. For every instrument pair `(i, j)` with `i <= j` (so the diagonal —
   each instrument against itself, always `1.0` — is included):
   build the two aligned return lists over the common date set (sorted by
   `ts_event` so both lists are in the same order), then
   `statistics.correlation(returns_i, returns_j)`. Mirror the result into
   both `(i, j)` and `(j, i)` keys in the output dict (a full matrix, not
   just the upper triangle — simpler for a consumer to look up `(a, b)`
   without checking key order).
5. Return the dict.

**Why a global common-date intersection, not per-pair:** a correlation
matrix computed from per-pair-different date windows is not guaranteed to
be a mathematically valid correlation matrix (e.g. for later multivariate
uses like portfolio variance or PCA, which this platform's Phase 3/4 work
will eventually want) — the eigenvalues/positive-semi-definiteness
guarantees only hold when every entry is computed from the same
observation set. With 4 instruments across 2 venues, 237 common dates is
already confirmed to exist, so this constraint costs little data.

**Why `dict[tuple[str, str], float]`, not a `pandas.DataFrame`:** matches
sub-9's "single entry-point function" pattern, and a flat dict of
`(instrument_a, instrument_b) -> correlation` is already shaped like a
weighted-edge list — directly usable as graph edges when a future
dashboard renders this as a relationship graph, with no reshaping needed.

**Why `statistics.correlation` (stdlib), not numpy/pandas:** Python's
`statistics` module has had `correlation()` since 3.10, and this project
already requires `>=3.11` — no new dependency needed for a 4-instrument,
single-pass computation. `numpy`/`pandas` are available transitively via
`nautilus_trader` but aren't declared as this project's own dependencies;
introducing a new explicit dependency for this would be premature for
this sub-project's scope.

## Error Handling

- Fewer than 2 instruments requested -> `ValueError`.
- Mismatched `instrument_ids`/`bar_type_strs` lengths -> `ValueError`.
- No bars found for a given instrument/bar_type/date range -> `ValueError`
  naming that instrument (mirrors sub-9's `run_backtest` error message
  shape).
- Fewer than 2 common dates across all instruments -> `ValueError` with a
  message distinguishing this from "no data at all" (i.e., each
  instrument individually has data, but their trading calendars don't
  overlap enough).

## Testing

- `tests/test_returns.py`: unit tests for `compute_returns` using a small
  hand-built `Bar` list with known close prices, asserting the exact
  returned pct-return values and that the first bar contributes no entry.
- `tests/test_correlation.py`: builds synthetic bars for 3 instruments
  with engineered close-price series — one pair perfectly positively
  correlated (identical price path), one pair perfectly negatively
  correlated (inverted price path), one pair with no engineered
  relationship — written into a temp `ParquetDataCatalog`, then asserts
  `corr_matrix(...)` returns values close to `1.0`, `-1.0`, and something
  in between respectively (with a small float tolerance), plus the
  fewer-than-2-instruments and no-common-dates `ValueError` cases.
- Manual end-to-end verification (not automated, mirrors sub-1/8/9's
  pattern): run `corr_matrix` against the real 4-instrument catalog data
  refreshed above, confirm every value is in `[-1.0, 1.0]`, and eyeball
  whether same-market pairs (`005930`↔`000660`, `AAPL`↔`MSFT`) show higher
  correlation than cross-market pairs — not asserted automatically, just a
  sanity narrative for the implementer to report.

## Open Questions / Risks Carried Forward

- The global-common-date design means adding a 5th instrument with a
  sparser trading calendar than the current 4 could shrink the common
  date set for *every* pair, not just pairs involving the new instrument.
  Acceptable for this sub-project's 4-instrument scope; revisit if a much
  larger instrument universe is added later (e.g. switch to per-pair dates
  with an explicit warning, or require a minimum overlap threshold).
- This module's output is a snapshot for one fixed date range, computed
  on demand — no caching, no incremental update story. Fine for this
  sub-project's scope (mirrors `run_backtest`'s same one-shot nature); a
  future dashboard backend sub-project would need to decide whether to
  cache or recompute these on each view.
