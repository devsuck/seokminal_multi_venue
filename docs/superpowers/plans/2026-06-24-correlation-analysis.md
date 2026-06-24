# Cross-Asset Correlation Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `correlation_analysis/`, a single `corr_matrix(...)`
function that queries multiple instruments' bars from the existing
`ParquetDataCatalog` (KIS + IB venues) and returns a pairwise Pearson
correlation matrix of their daily returns, computed over the date range
common to all requested instruments.

**Architecture:** Two small files. `returns.py`'s `compute_returns`
converts a sorted list of daily `Bar` objects into close-to-close pct
returns keyed by `ts_event` (nanoseconds) — no date-object conversion
needed, since both venues' bars already normalize to the same
midnight-UTC timestamp scheme. `correlation.py`'s `corr_matrix` queries
each instrument's bars via the same catalog-query pattern sub-9's
`run_backtest` already established, computes each instrument's returns,
intersects all of their `ts_event` keys into one common date set, and
computes every pairwise (and self) Pearson correlation over that common
set using the standard library's `statistics.correlation`.

**Tech Stack:** `nautilus_trader` (already a dependency) —
`nautilus_trader.persistence.catalog.ParquetDataCatalog`,
`nautilus_trader.model.data.Bar`. Python stdlib `statistics.correlation`
(available since 3.10; this project requires `>=3.11`) — no new
dependency. `pytest` (already configured).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-24-correlation-analysis-design.md`.
- `corr_matrix` requires `len(instrument_ids) >= 2` and
  `len(instrument_ids) == len(bar_type_strs)` — else `ValueError`.
- Correlation is computed over the date range (`ts_event` set) common to
  **all** requested instruments — never per-pair date windows. If that
  global intersection has fewer than 2 dates, raise `ValueError` (not the
  stdlib's own less-clear error).
- Output includes the full matrix, both `(a, b)` and `(b, a)` keys, plus
  the diagonal (`(a, a) -> 1.0`) — not just the upper triangle.
- `compute_returns` is keyed by `ts_event` (int nanoseconds), not a
  converted `datetime.date` — both KIS and IB daily bars already share
  the same midnight-UTC timestamp convention, confirmed by the existing
  `map_kis_daily_bar` (sub-1) and `map_ib_daily_bar` (sub-8) code.
- No new data ingestion code, no factor/beta computation, no
  `pandas`/`numpy` as new explicit dependencies, no more than the 4
  already-ingested instruments — all per spec's "Out of scope".
- The catalog already contains 4 real instruments with overlapping dates
  (confirmed directly: `005930.XKRX` and `AAPL.NASDAQ` share 237 common
  trading dates as of this plan's writing) — this plan's tests use
  synthetic data in a temp catalog; only the optional manual verification
  step (Task 3) touches the real `./catalog`.
- Verified directly in this environment (not assumed from docs):
  - `statistics.correlation(x, y)` (stdlib) returns `1.0` for identical
    sequences, `-1.0` for inverted sequences, and raises
    `StatisticsError: correlation requires at least two data points` for
    length-1 inputs.

---

### Task 1: `compute_returns`

**Files:**
- Create: `correlation_analysis/__init__.py` (empty)
- Create: `correlation_analysis/returns.py`
- Test: `tests/test_returns.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure function over
  `nautilus_trader.model.data.Bar`).
- Produces (consumed by Task 2): `compute_returns(bars: list[Bar]) ->
  dict[int, float]` — keys are each bar's `ts_event` (int, nanoseconds,
  skipping the first bar in the input since it has no prior close to
  compare against), values are `(close / prior_close) - 1.0`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_returns.py
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from correlation_analysis.returns import compute_returns

BAR_TYPE = "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL"


def _bar(price: float, ts: int) -> Bar:
    return Bar(
        bar_type=BarType.from_str(BAR_TYPE),
        open=Price.from_str(f"{price:.2f}"),
        high=Price.from_str(f"{price + 1:.2f}"),
        low=Price.from_str(f"{price - 1:.2f}"),
        close=Price.from_str(f"{price:.2f}"),
        volume=Quantity.from_str("10"),
        ts_event=ts,
        ts_init=ts,
    )


def test_compute_returns_skips_first_bar():
    bars = [_bar(100.0, 0)]

    returns = compute_returns(bars)

    assert returns == {}


def test_compute_returns_computes_pct_change_keyed_by_ts_event():
    bars = [_bar(100.0, 0), _bar(110.0, 1), _bar(99.0, 2)]

    returns = compute_returns(bars)

    assert returns == {
        1: 0.1,
        2: pytest.approx(99.0 / 110.0 - 1.0),
    }


def test_compute_returns_on_empty_list():
    assert compute_returns([]) == {}
```

Note: the second test uses `pytest.approx` for the second value (floating
point division) — add `import pytest` at the top of the file alongside the
other imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_returns.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'correlation_analysis'`

- [ ] **Step 3: Implement `correlation_analysis/returns.py`**

```python
# correlation_analysis/returns.py
from nautilus_trader.model.data import Bar


def compute_returns(bars: list[Bar]) -> dict[int, float]:
    returns: dict[int, float] = {}
    for i in range(1, len(bars)):
        prior_close = bars[i - 1].close.as_double()
        close = bars[i].close.as_double()
        returns[bars[i].ts_event] = (close / prior_close) - 1.0
    return returns
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_returns.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add correlation_analysis/__init__.py correlation_analysis/returns.py tests/test_returns.py
git commit -m "feat: add compute_returns for daily close-to-close pct returns"
```

---

### Task 2: `corr_matrix`

**Files:**
- Create: `correlation_analysis/correlation.py`
- Test: `tests/test_correlation.py`

**Interfaces:**
- Consumes: `compute_returns(bars: list[Bar]) -> dict[int, float]` (Task
  1); `nautilus_trader.persistence.catalog.ParquetDataCatalog`.
- Produces: `corr_matrix(instrument_ids: list[str], bar_type_strs:
  list[str], start_ns: int, end_ns: int, catalog_path: str) ->
  dict[tuple[str, str], float]`. No other task in this plan depends on
  this.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_correlation.py
import tempfile

import pytest
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from correlation_analysis.correlation import corr_matrix


def _equity(symbol: str) -> Equity:
    return Equity(
        instrument_id=InstrumentId.from_str(f"{symbol}.NASDAQ"),
        raw_symbol=Symbol(symbol),
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def _bar_type_str(symbol: str) -> str:
    return f"{symbol}.NASDAQ-1-DAY-LAST-EXTERNAL"


def _bar(symbol: str, price: float, ts: int) -> Bar:
    return Bar(
        bar_type=BarType.from_str(_bar_type_str(symbol)),
        open=Price.from_str(f"{price:.2f}"),
        high=Price.from_str(f"{price + 1:.2f}"),
        low=Price.from_str(f"{price - 1:.2f}"),
        close=Price.from_str(f"{price:.2f}"),
        volume=Quantity.from_str("10"),
        ts_event=ts,
        ts_init=ts,
    )


def test_corr_matrix_identifies_perfect_positive_and_negative_correlation():
    # AAA tracks a rising price path; BBB is the exact inverse; CCC is unrelated.
    aaa_prices = [100, 102, 101, 105, 103, 108]
    bbb_prices = [100, 98, 99, 95, 97, 92]
    ccc_prices = [50, 51.56, 53.33, 53.29, 51.32, 50.5]

    aaa_bars = [_bar("AAA", p, i * 86_400_000_000_000) for i, p in enumerate(aaa_prices)]
    bbb_bars = [_bar("BBB", p, i * 86_400_000_000_000) for i, p in enumerate(bbb_prices)]
    ccc_bars = [_bar("CCC", p, i * 86_400_000_000_000) for i, p in enumerate(ccc_prices)]

    with tempfile.TemporaryDirectory() as tmp_dir:
        catalog = ParquetDataCatalog(tmp_dir)
        catalog.write_data([_equity("AAA"), _equity("BBB"), _equity("CCC")])
        catalog.write_data(aaa_bars + bbb_bars + ccc_bars)

        result = corr_matrix(
            instrument_ids=["AAA.NASDAQ", "BBB.NASDAQ", "CCC.NASDAQ"],
            bar_type_strs=[_bar_type_str("AAA"), _bar_type_str("BBB"), _bar_type_str("CCC")],
            start_ns=0,
            end_ns=aaa_bars[-1].ts_event,
            catalog_path=tmp_dir,
        )

    assert result[("AAA.NASDAQ", "AAA.NASDAQ")] == pytest.approx(1.0)
    assert result[("AAA.NASDAQ", "BBB.NASDAQ")] == pytest.approx(-1.0, abs=0.05)
    assert result[("BBB.NASDAQ", "AAA.NASDAQ")] == pytest.approx(-1.0, abs=0.05)
    assert -0.9 < result[("AAA.NASDAQ", "CCC.NASDAQ")] < 0.9


def test_corr_matrix_rejects_fewer_than_two_instruments():
    with pytest.raises(ValueError, match="at least 2"):
        corr_matrix(
            instrument_ids=["AAA.NASDAQ"],
            bar_type_strs=[_bar_type_str("AAA")],
            start_ns=0,
            end_ns=1,
            catalog_path="./irrelevant",
        )


def test_corr_matrix_raises_on_no_common_dates():
    aaa_bars = [_bar("AAA", 100 + i, i * 86_400_000_000_000) for i in range(5)]
    bbb_bars = [_bar("BBB", 100 + i, (i + 100) * 86_400_000_000_000) for i in range(5)]

    with tempfile.TemporaryDirectory() as tmp_dir:
        catalog = ParquetDataCatalog(tmp_dir)
        catalog.write_data([_equity("AAA"), _equity("BBB")])
        catalog.write_data(aaa_bars + bbb_bars)

        with pytest.raises(ValueError, match="common"):
            corr_matrix(
                instrument_ids=["AAA.NASDAQ", "BBB.NASDAQ"],
                bar_type_strs=[_bar_type_str("AAA"), _bar_type_str("BBB")],
                start_ns=0,
                end_ns=200 * 86_400_000_000_000,
                catalog_path=tmp_dir,
            )
```

Note: the `AAA`↔`BBB` correlation tolerance is `abs=0.05` rather than an
exact `-1.0` because the returns are computed from price *levels* chosen
to be visibly inverse but not algebraically perfect inverses (simpler to
read than engineering exact mirrored percentage changes) — this still
distinguishes strong negative correlation from the unrelated `CCC` pair
clearly.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_correlation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'correlation_analysis.correlation'`

- [ ] **Step 3: Implement `correlation_analysis/correlation.py`**

```python
# correlation_analysis/correlation.py
import statistics

from nautilus_trader.persistence.catalog import ParquetDataCatalog

from correlation_analysis.returns import compute_returns


def corr_matrix(
    instrument_ids: list[str],
    bar_type_strs: list[str],
    start_ns: int,
    end_ns: int,
    catalog_path: str,
) -> dict[tuple[str, str], float]:
    if len(instrument_ids) < 2:
        raise ValueError(
            f"corr_matrix requires at least 2 instruments, got {len(instrument_ids)}"
        )
    if len(instrument_ids) != len(bar_type_strs):
        raise ValueError(
            "instrument_ids and bar_type_strs must be the same length: "
            f"{len(instrument_ids)} != {len(bar_type_strs)}"
        )

    catalog = ParquetDataCatalog(catalog_path)

    returns_by_instrument: dict[str, dict[int, float]] = {}
    for instrument_id, bar_type_str in zip(instrument_ids, bar_type_strs):
        all_bars = catalog.bars(bar_types=[bar_type_str])
        bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
        if not bars:
            raise ValueError(
                f"no bars found for {instrument_id!r} {bar_type_str!r} "
                f"in range [{start_ns}, {end_ns}]"
            )
        returns_by_instrument[instrument_id] = compute_returns(bars)

    common_dates = set(returns_by_instrument[instrument_ids[0]].keys())
    for instrument_id in instrument_ids[1:]:
        common_dates &= set(returns_by_instrument[instrument_id].keys())

    if len(common_dates) < 2:
        raise ValueError(
            f"fewer than 2 dates common to all instruments {instrument_ids}: "
            f"found {len(common_dates)}"
        )

    sorted_dates = sorted(common_dates)
    aligned_returns = {
        instrument_id: [returns_by_instrument[instrument_id][ts] for ts in sorted_dates]
        for instrument_id in instrument_ids
    }

    result: dict[tuple[str, str], float] = {}
    for i, instrument_a in enumerate(instrument_ids):
        for instrument_b in instrument_ids[i:]:
            correlation = statistics.correlation(
                aligned_returns[instrument_a], aligned_returns[instrument_b]
            )
            result[(instrument_a, instrument_b)] = correlation
            result[(instrument_b, instrument_a)] = correlation

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_correlation.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing suite + this plan's 6 new tests across
both tasks: 3 in `test_returns.py`, 3 in `test_correlation.py`)

- [ ] **Step 6: Commit**

```bash
git add correlation_analysis/correlation.py tests/test_correlation.py
git commit -m "feat: add corr_matrix for cross-asset Pearson correlation"
```

---

### Task 3: Update progress ledger, dispatch final review, manual verification

**Files:** none (bookkeeping only)

- [ ] **Step 1: Append to the progress ledger**

Append to `.superpowers/sdd/progress.md`:

```
--- Sub-project 10: correlation analysis (spec 141805d, plan <this commit>) ---
Task 1: complete (correlation_analysis/returns.py, commit <hash>)
Task 2: complete (correlation_analysis/correlation.py, commit <hash>)
```

- [ ] **Step 2: Dispatch the final whole-branch review**

Per `superpowers:subagent-driven-development`'s process: use the commit
right before Task 1 (the spec commit, `141805d`) as the base. Run
`scripts/review-package 141805d HEAD` (from the `subagent-driven-development`
skill's directory) as the diff package, dispatch a code-reviewer subagent on
the most capable available model per that skill's `code-reviewer.md`
template, and resolve any Critical/Important findings before considering
sub-project 10 complete.

- [ ] **Step 3: Manual end-to-end verification against real catalog data (not automated)**

```python
from correlation_analysis.correlation import corr_matrix

result = corr_matrix(
    instrument_ids=["005930.XKRX", "000660.XKRX", "AAPL.NASDAQ", "MSFT.NASDAQ"],
    bar_type_strs=[
        "005930.XKRX-1-DAY-LAST-EXTERNAL",
        "000660.XKRX-1-DAY-LAST-EXTERNAL",
        "AAPL.NASDAQ-1-DAY-LAST-EXTERNAL",
        "MSFT.NASDAQ-1-DAY-LAST-EXTERNAL",
    ],
    start_ns=0,
    end_ns=9_999_999_999_999_999_999,
    catalog_path="./catalog",
)
for pair, value in sorted(result.items()):
    print(pair, value)
```

Confirm every value is in `[-1.0, 1.0]`. Report (not assert
automatically) whether the same-market pairs (`005930.XKRX`↔`000660.XKRX`,
`AAPL.NASDAQ`↔`MSFT.NASDAQ`) show higher correlation than the cross-market
pairs — this is a sanity narrative for the report, not a pass/fail check,
since real market correlation can vary.

## Out of scope (reminder, per spec)

Do not add: factor/beta computation, the dashboard-backend half of Phase
3, any new data ingestion code, more than the 4 already-ingested
instruments, or `pandas`/`numpy` as new explicit dependencies. These
belong to a later sub-project if ever needed.
