# Index Data Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest the KOSPI index and the SPY ETF into the existing `ParquetDataCatalog`, giving a later sub-project (factor/beta exposure analysis) a market benchmark to compute against.

**Architecture:** Extend the existing KIS/IB client and data-provider modules with index-specific additions (new KIS endpoint method, new `IndexInstrument` builder, new bar mapper, a venue-parameterized `build_us_equity`), then two ingestion entry points (one new file for KOSPI, one new CLI flag on the existing IB entry point for SPY).

**Tech Stack:** Python, `requests` (KIS), `ib_async` (IB), `nautilus_trader` (`IndexInstrument`, `Equity`, `ParquetDataCatalog`), `pytest`.

## Global Constraints

- No changes to `condition_engine/`, `backtest_runner/`, `correlation_analysis/`, or `api_server/` — this plan only touches `backends/kis/client.py`, `adapters/data_provider.py`, ingestion entry points, and their tests.
- `get_daily_price` (existing KIS stock method) is untouched — `get_daily_index_price` is a new, separate method.
- `build_us_equity`'s new `venue` parameter defaults to `"NASDAQ"` — every existing call site (sub-1, sub-8, sub-9, sub-11's tests) must continue to produce identical results with no changes to those call sites.
- KIS index field names (`bstp_nmix_oprc`/`bstp_nmix_hgpr`/`bstp_nmix_lwpr`/`bstp_nmix_prpr`) are sourced from documentation, not yet verified live — Task 1's manual verification step must confirm them against the real API and the implementer must fix the mapper in the same task if they differ (mirroring sub-1/sub-4's precedent for KIS field-name surprises).
- `IndexInstrument` is `nautilus_trader.model.instruments.IndexInstrument` — confirmed present in the installed `nautilus_trader` version (`from nautilus_trader.model.instruments import IndexInstrument`).

---

### Task 1: KIS index client method + KOSPI instrument builder

**Files:**
- Modify: `backends/kis/client.py` (add `get_daily_index_price`)
- Modify: `adapters/data_provider.py` (add `build_kospi_index`, `map_kis_index_daily_bar`)
- Test: `tests/test_client.py` (add tests for `get_daily_index_price`)
- Test: `tests/test_data_provider.py` (add tests for `build_kospi_index`, `map_kis_index_daily_bar`)

**Interfaces:**
- Consumes: `backends.kis.auth.KISAuth` (existing, unchanged), `nautilus_trader.model.instruments.IndexInstrument`, `nautilus_trader.model.data.Bar`/`BarType`, `nautilus_trader.model.identifiers.InstrumentId`/`Symbol`, `nautilus_trader.model.objects.Price`/`Quantity`, `nautilus_trader.model.currencies.KRW`, `nautilus_trader.core.datetime.dt_to_unix_nanos`.
- Produces: `KISClient.get_daily_index_price(index_code: str, start: str, end: str) -> list[dict]` (used by Task 3's `data_ingestion_kospi.py`); `build_kospi_index() -> IndexInstrument` and `map_kis_index_daily_bar(row: dict, bar_type: BarType, price_precision: int) -> Bar` (both used by Task 3).

- [ ] **Step 1: Write the failing tests for `get_daily_index_price`**

Append to `tests/test_client.py`:

```python
def _index_row(date: str, close: str = "265032") -> dict:
    return {
        "stck_bsop_date": date,
        "bstp_nmix_oprc": "264500",
        "bstp_nmix_hgpr": "265500",
        "bstp_nmix_lwpr": "264000",
        "bstp_nmix_prpr": close,
        "acml_vol": "500000000",
    }


def test_get_daily_index_price_single_page_returns_rows_oldest_first():
    session = MagicMock()
    rows_newest_first = [_index_row("20240103"), _index_row("20240102"), _index_row("20240101")]
    session.get.return_value = _mock_response(rows_newest_first)
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_index_price("0001", "20240101", "20240103")

    assert [r["stck_bsop_date"] for r in result] == ["20240101", "20240102", "20240103"]
    call_kwargs = session.get.call_args.kwargs
    assert call_kwargs["params"]["FID_COND_MRKT_DIV_CODE"] == "U"
    assert call_kwargs["params"]["FID_INPUT_ISCD"] == "0001"


def test_get_daily_index_price_skips_blank_rows():
    session = MagicMock()
    rows = [
        _index_row("20240101"),
        {
            "stck_bsop_date": "",
            "bstp_nmix_oprc": "",
            "bstp_nmix_hgpr": "",
            "bstp_nmix_lwpr": "",
            "bstp_nmix_prpr": "",
            "acml_vol": "",
        },
    ]
    session.get.return_value = _mock_response(rows)
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_index_price("0001", "20240101", "20240101")

    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client.py -k index -v`
Expected: FAIL with `AttributeError: 'KISClient' object has no attribute 'get_daily_index_price'`

- [ ] **Step 3: Implement `get_daily_index_price`**

In `backends/kis/client.py`, add these module-level constants near the existing `DAILY_PRICE_PATH`/`DAILY_PRICE_TR_ID`:

```python
DAILY_INDEX_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
DAILY_INDEX_PRICE_TR_ID = "FHPUP02120000"
```

Add this method to the `KISClient` class, alongside `get_daily_price` (the pagination logic is intentionally duplicated rather than shared, since the index endpoint's response field names differ and KOSPI's single-year lookback windows are short enough that the existing `get_daily_price`'s multi-page stress-tested logic isn't needed here — a single, simpler loop is clearer):

```python
    def get_daily_index_price(self, index_code: str, start: str, end: str) -> list[dict]:
        all_rows: list[dict] = []
        window_end = end

        while True:
            page = self._fetch_index_page(index_code, start, window_end)
            if not page:
                break

            all_rows.extend(page)

            oldest_date_in_page = page[0]["stck_bsop_date"]
            if len(page) < PAGE_SIZE or oldest_date_in_page <= start:
                break

            window_end = _previous_day(oldest_date_in_page)
            time.sleep(self._request_delay_seconds)

        all_rows.sort(key=lambda row: row["stck_bsop_date"])
        return [row for row in all_rows if start <= row["stck_bsop_date"] <= end]

    def _fetch_index_page(self, index_code: str, start: str, end: str) -> list[dict]:
        try:
            response = self._request_index_page(index_code, start, end)
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 401:
                raise
            self._auth.invalidate()
            response = self._request_index_page(index_code, start, end)

        payload = response.json()
        rt_cd = payload.get("rt_cd")
        if rt_cd != "0":
            raise RuntimeError(f"KIS API error rt_cd={rt_cd}: {payload.get('msg1')}")
        rows = payload.get("output2", [])
        non_blank = [row for row in rows if row.get("stck_bsop_date")]
        non_blank.sort(key=lambda row: row["stck_bsop_date"])
        return non_blank

    def _request_index_page(self, index_code: str, start: str, end: str) -> requests.Response:
        token = self._auth.get_access_token()
        response = self._session.get(
            f"{self._base_url}{DAILY_INDEX_PRICE_PATH}",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
                "tr_id": DAILY_INDEX_PRICE_TR_ID,
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": index_code,
                "FID_INPUT_DATE_1": start,
                "FID_INPUT_DATE_2": end,
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
        response.raise_for_status()
        return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client.py -v`
Expected: all tests pass, including the 2 new index tests.

- [ ] **Step 5: Write the failing tests for `build_kospi_index` and `map_kis_index_daily_bar`**

Append to `tests/test_data_provider.py` (add `from nautilus_trader.model.instruments import IndexInstrument` to the imports, and add `build_kospi_index`, `map_kis_index_daily_bar` to the existing `from adapters.data_provider import (...)` block):

```python
def test_build_kospi_index_has_expected_fields():
    index = build_kospi_index()

    assert isinstance(index, IndexInstrument)
    assert index.id == InstrumentId.from_str("KOSPI.XKRX")
    assert str(index.quote_currency) == "KRW"
    assert index.price_precision == 2


def test_map_kis_index_daily_bar_converts_row_to_bar():
    bar_type = bar_type_for(InstrumentId.from_str("KOSPI.XKRX"))
    row = {
        "stck_bsop_date": "20240102",
        "bstp_nmix_oprc": "264500",
        "bstp_nmix_hgpr": "265500",
        "bstp_nmix_lwpr": "264000",
        "bstp_nmix_prpr": "265032",
        "acml_vol": "500000000",
    }

    bar = map_kis_index_daily_bar(row, bar_type, price_precision=2)

    assert bar.bar_type == bar_type
    assert bar.open.as_double() == 2645.00
    assert bar.high.as_double() == 2655.00
    assert bar.low.as_double() == 2640.00
    assert bar.close.as_double() == 2650.32
    assert bar.volume.as_double() == 500_000_000.0
    assert bar.ts_event == 1704153600000000000
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_data_provider.py -k kospi -v`
Expected: FAIL with `ImportError: cannot import name 'build_kospi_index'`

- [ ] **Step 7: Implement `build_kospi_index` and `map_kis_index_daily_bar`**

In `adapters/data_provider.py`, add `IndexInstrument` to the existing `from nautilus_trader.model.instruments import Equity` import line (becomes `from nautilus_trader.model.instruments import Equity, IndexInstrument`). Then add, alongside `build_xkrx_equity`:

```python
def build_kospi_index() -> IndexInstrument:
    now_ns = dt_to_unix_nanos(dt.datetime.now(dt.timezone.utc))
    return IndexInstrument(
        instrument_id=InstrumentId.from_str("KOSPI.XKRX"),
        raw_symbol=Symbol("0001"),
        currency=KRW,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        size_precision=0,
        size_increment=Quantity.from_int(1),
        ts_event=now_ns,
        ts_init=now_ns,
    )
```

And alongside `map_kis_daily_bar`:

```python
def map_kis_index_daily_bar(row: dict, bar_type: BarType, price_precision: int) -> Bar:
    event_date = dt.datetime.strptime(row["stck_bsop_date"], "%Y%m%d").replace(
        tzinfo=dt.timezone.utc
    )
    ts_event = dt_to_unix_nanos(event_date)

    return Bar(
        bar_type=bar_type,
        open=Price(float(row["bstp_nmix_oprc"]) / 100, price_precision),
        high=Price(float(row["bstp_nmix_hgpr"]) / 100, price_precision),
        low=Price(float(row["bstp_nmix_lwpr"]) / 100, price_precision),
        close=Price(float(row["bstp_nmix_prpr"]) / 100, price_precision),
        volume=Quantity(float(row["acml_vol"]), 0),
        ts_event=ts_event,
        ts_init=ts_event,
    )
```

(Note the `/ 100`: KIS's index endpoint returns these fields scaled by 100 relative to the displayed index value — e.g. `"265032"` represents `2650.32` points. This must be confirmed against a real API response in Task 1's manual verification, per the Global Constraints note; if the live response is NOT scaled by 100, remove the `/ 100` division here and update this comment and the test's expected values accordingly.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_data_provider.py -v`
Expected: all tests pass, including the 2 new KOSPI tests.

- [ ] **Step 9: Commit**

```bash
git add backends/kis/client.py adapters/data_provider.py tests/test_client.py tests/test_data_provider.py
git commit -m "feat: add KIS index endpoint client method and KOSPI instrument builder"
```

---

### Task 2: `build_us_equity` venue parameter

**Files:**
- Modify: `adapters/data_provider.py:128-138` (`build_us_equity`)
- Test: `tests/test_data_provider.py` (extend the existing `build_us_equity` test, add a new one for the `venue` param)

**Interfaces:**
- Consumes: nothing new.
- Produces: `build_us_equity(symbol: str, venue: str = "NASDAQ") -> Equity` — used by Task 4's `--venue` CLI flag on `data_ingestion_ib.py`.

- [ ] **Step 1: Write the failing test for the new `venue` parameter**

Append to `tests/test_data_provider.py` (right after the existing `test_build_us_equity_has_expected_fields`):

```python
def test_build_us_equity_default_venue_is_nasdaq():
    equity = build_us_equity("AAPL")

    assert equity.id == InstrumentId.from_str("AAPL.NASDAQ")


def test_build_us_equity_accepts_explicit_venue():
    equity = build_us_equity("SPY", venue="ARCA")

    assert equity.id == InstrumentId.from_str("SPY.ARCA")
    assert str(equity.quote_currency) == "USD"
    assert equity.price_precision == 2
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `pytest tests/test_data_provider.py -k "venue" -v`
Expected: `test_build_us_equity_accepts_explicit_venue` FAILS with `TypeError: build_us_equity() got an unexpected keyword argument 'venue'`; `test_build_us_equity_default_venue_is_nasdaq` passes already (it's a regression check on existing behavior).

- [ ] **Step 3: Add the `venue` parameter**

In `adapters/data_provider.py`, change:

```python
def build_us_equity(symbol: str) -> Equity:
    now_ns = dt_to_unix_nanos(dt.datetime.now(dt.timezone.utc))
    return Equity(
        instrument_id=InstrumentId.from_str(f"{symbol}.NASDAQ"),
```

to:

```python
def build_us_equity(symbol: str, venue: str = "NASDAQ") -> Equity:
    now_ns = dt_to_unix_nanos(dt.datetime.now(dt.timezone.utc))
    return Equity(
        instrument_id=InstrumentId.from_str(f"{symbol}.{venue}"),
```

(No other lines in the function change — `raw_symbol`, `currency`, `price_precision`, etc. stay exactly as they are.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_provider.py -v`
Expected: all tests pass (full file, confirming no regression on `AAPL`/existing callers).

- [ ] **Step 5: Commit**

```bash
git add adapters/data_provider.py tests/test_data_provider.py
git commit -m "feat: add optional venue parameter to build_us_equity"
```

---

### Task 3: KOSPI ingestion entry point

**Files:**
- Create: `data_ingestion_kospi.py`
- Test: `tests/test_data_ingestion_kospi.py`

**Interfaces:**
- Consumes: `backends.kis.client.KISClient.get_daily_index_price` (Task 1), `adapters.data_provider.build_kospi_index`, `adapters.data_provider.map_kis_index_daily_bar`, `adapters.data_provider.bar_type_for` (Task 1/existing).
- Produces: `run_ingestion_kospi(start: str, end: str, catalog_path: str, client: KISClient) -> int` — a standalone function, plus a `main()` CLI entry point mirroring `data_ingestion.py`'s shape.

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_ingestion_kospi.py`:

```python
import tempfile
from unittest.mock import MagicMock

from nautilus_trader.persistence.catalog import ParquetDataCatalog

from data_ingestion_kospi import run_ingestion_kospi


def test_run_ingestion_kospi_writes_instrument_and_bars_to_catalog():
    client = MagicMock()
    client.get_daily_index_price.return_value = [
        {
            "stck_bsop_date": "20240102",
            "bstp_nmix_oprc": "264500",
            "bstp_nmix_hgpr": "265500",
            "bstp_nmix_lwpr": "264000",
            "bstp_nmix_prpr": "265032",
            "acml_vol": "500000000",
        },
        {
            "stck_bsop_date": "20240103",
            "bstp_nmix_oprc": "265100",
            "bstp_nmix_hgpr": "266000",
            "bstp_nmix_lwpr": "264800",
            "bstp_nmix_prpr": "265800",
            "acml_vol": "480000000",
        },
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        written = run_ingestion_kospi(
            start="20240101",
            end="20240103",
            catalog_path=tmp_dir,
            client=client,
        )

        assert written == 2

        catalog = ParquetDataCatalog(tmp_dir)
        instruments = catalog.instruments()
        assert len(instruments) == 1
        assert str(instruments[0].id) == "KOSPI.XKRX"

        bars = catalog.bars()
        assert len(bars) == 2
        assert bars[0].close.as_double() == 2650.32
        assert bars[1].close.as_double() == 2658.00

    client.get_daily_index_price.assert_called_once_with("0001", "20240101", "20240103")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_ingestion_kospi.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_ingestion_kospi'`

- [ ] **Step 3: Write `data_ingestion_kospi.py`**

```python
import argparse
import datetime as dt
import os

from dotenv import load_dotenv
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for, build_kospi_index, map_kis_index_daily_bar
from backends.kis.client import KISClient

KOSPI_INDEX_CODE = "0001"


def run_ingestion_kospi(start: str, end: str, catalog_path: str, client: KISClient) -> int:
    instrument = build_kospi_index()
    bar_type = bar_type_for(instrument.id)

    rows = client.get_daily_index_price(KOSPI_INDEX_CODE, start, end)
    bars = [
        map_kis_index_daily_bar(row, bar_type, instrument.price_precision)
        for row in rows
    ]

    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([instrument])
    catalog.write_data(bars)

    return len(bars)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Ingest KOSPI daily index bars into a ParquetDataCatalog")
    parser.add_argument("--index-code", default=KOSPI_INDEX_CODE)
    parser.add_argument("--start", default=(dt.date.today() - dt.timedelta(days=365)).strftime("%Y%m%d"))
    parser.add_argument("--end", default=dt.date.today().strftime("%Y%m%d"))
    parser.add_argument("--catalog-path", default="./catalog")
    args = parser.parse_args()

    app_key = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    client = KISClient(app_key=app_key, app_secret=app_secret)

    written = run_ingestion_kospi(args.start, args.end, args.catalog_path, client)
    print(f"Wrote {written} bars for KOSPI ({args.start}-{args.end}) to {args.catalog_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_data_ingestion_kospi.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_ingestion_kospi.py tests/test_data_ingestion_kospi.py
git commit -m "feat: add data_ingestion_kospi.py entry point for KOSPI index bars"
```

---

### Task 4: SPY venue support in IB ingestion entry point

**Files:**
- Modify: `data_ingestion_ib.py`
- Test: `tests/test_data_ingestion_ib.py`

**Interfaces:**
- Consumes: `adapters.data_provider.build_us_equity(symbol, venue)` (Task 2).
- Produces: `run_ingestion_ib(symbol, end_date, duration, catalog_path, client, venue="NASDAQ")` (new optional `venue` parameter); `--venue` CLI flag on `main()`.

- [ ] **Step 1: Write the failing test for the `venue` parameter**

Append to `tests/test_data_ingestion_ib.py`:

```python
async def test_run_ingestion_ib_accepts_explicit_venue():
    client = AsyncMock()
    client.get_daily_bars.return_value = [
        BarData(date=dt.date(2024, 1, 2), open=470.0, high=472.0, low=469.0, close=471.5, volume=80000.0),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        written = await run_ingestion_ib(
            symbol="SPY",
            end_date="20240102 23:59:59",
            duration="1 Y",
            catalog_path=tmp_dir,
            client=client,
            venue="ARCA",
        )

        assert written == 1

        catalog = ParquetDataCatalog(tmp_dir)
        instruments = catalog.instruments()
        assert len(instruments) == 1
        assert str(instruments[0].id) == "SPY.ARCA"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_ingestion_ib.py -v`
Expected: the new test FAILS with `TypeError: run_ingestion_ib() got an unexpected keyword argument 'venue'`; the existing test still passes.

- [ ] **Step 3: Add the `venue` parameter**

In `data_ingestion_ib.py`, change:

```python
async def run_ingestion_ib(
    symbol: str, end_date: str, duration: str, catalog_path: str, client: IBClient
) -> int:
    instrument = build_us_equity(symbol)
```

to:

```python
async def run_ingestion_ib(
    symbol: str, end_date: str, duration: str, catalog_path: str, client: IBClient,
    venue: str = "NASDAQ",
) -> int:
    instrument = build_us_equity(symbol, venue=venue)
```

Then in `main()`, add a `--venue` argument right after `--symbol`:

```python
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--venue", default="NASDAQ")
```

and pass it through in the `asyncio.run(...)` call:

```python
    written = asyncio.run(
        run_ingestion_ib(args.symbol, args.end_date, args.duration, args.catalog_path, client, venue=args.venue)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_ingestion_ib.py -v`
Expected: both tests pass (existing `AAPL.NASDAQ` test unaffected, new `SPY.ARCA` test passes).

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `pytest -v`
Expected: all tests pass (previous full-suite count + 2 (Task 1 KIS index) + 2 (Task 1 KOSPI builder) + 2 (Task 2 venue) + 1 (Task 3 ingestion) + 1 (Task 4 venue ingestion) = +8 new tests, none broken).

- [ ] **Step 6: Commit**

```bash
git add data_ingestion_ib.py tests/test_data_ingestion_ib.py
git commit -m "feat: add venue parameter to data_ingestion_ib.py for SPY support"
```

---

### Task 5: Manual end-to-end verification

**Files:** none (verification only, no code changes expected unless the KIS field-name/scaling assumption from Task 1 turns out wrong, in which case fix `map_kis_index_daily_bar` and its test in place).

**Interfaces:** none.

- [ ] **Step 1: Run the real KOSPI ingestion**

Run (from `~/nautilus-multi-venue`, during/after Korean market hours for freshest data, but any day works since this is historical daily data):

```bash
python3 data_ingestion_kospi.py
```

Expected: prints `Wrote N bars for KOSPI (...) to ./catalog` with `N > 0`.

If the command fails or the values look obviously wrong (e.g. an index value off by 100x — too small like `26.50` or too large like `265032.00` instead of `~2650`), inspect the raw KIS response (add a temporary `print(rows[0])` in `get_daily_index_price` or test interactively) and fix `map_kis_index_daily_bar`'s `/ 100` scaling assumption in `adapters/data_provider.py` accordingly — update the Task 1 test's expected values to match, then re-run `pytest tests/test_data_provider.py -v` before continuing.

- [ ] **Step 2: Run the real SPY ingestion**

Run (from `~/nautilus-multi-venue`, with IB TWS paper account running on port 7497):

```bash
python3 data_ingestion_ib.py --symbol SPY --venue ARCA
```

Expected: prints `Wrote N bars for SPY (...) to ./catalog` with `N > 0`.

- [ ] **Step 3: Confirm both new instruments are in the catalog with correct IDs**

Run:

```bash
python3 -c "
from nautilus_trader.persistence.catalog import ParquetDataCatalog
catalog = ParquetDataCatalog('./catalog')
ids = sorted(str(i.id) for i in catalog.instruments())
print(ids)
"
```

Expected: output includes `'KOSPI.XKRX'` and `'SPY.ARCA'` alongside the 4 pre-existing instrument IDs (6 total).

- [ ] **Step 4: Confirm date-range overlap with existing instruments**

Run:

```bash
python3 -c "
from nautilus_trader.persistence.catalog import ParquetDataCatalog
catalog = ParquetDataCatalog('./catalog')

def dates(instrument_id, bar_type_str):
    bars = catalog.bars(bar_types=[bar_type_str])
    return {b.ts_event for b in bars}

kospi_dates = dates('KOSPI.XKRX', 'KOSPI.XKRX-1-DAY-LAST-EXTERNAL')
krx_dates = dates('005930.XKRX', '005930.XKRX-1-DAY-LAST-EXTERNAL')
spy_dates = dates('SPY.ARCA', 'SPY.ARCA-1-DAY-LAST-EXTERNAL')
us_dates = dates('AAPL.NASDAQ', 'AAPL.NASDAQ-1-DAY-LAST-EXTERNAL')

print('KOSPI vs 005930 common dates:', len(kospi_dates & krx_dates))
print('SPY vs AAPL common dates:', len(spy_dates & us_dates))
"
```

Expected: both common-date counts are well above 0 (ideally 200+, matching the existing 4-instrument catalog's established overlap). If either is 0, re-run Step 1 or Step 2 with `--start`/`--end` (KOSPI) or `--end-date`/`--duration` (SPY) adjusted to match the other instruments' default "last 365 days" window, per the sub-10 lesson already documented in this project's ledger.

- [ ] **Step 5: Record completion**

Append to `.superpowers/sdd/progress.md`:

```
--- Sub-project 13: index data ingestion (spec d0192d4, plan <this commit>) ---
Manual end-to-end verification: complete (date). KOSPI.XKRX and SPY.ARCA both ingested into ./catalog with non-empty bars, confirmed overlapping date ranges with the 4 pre-existing instruments. [Note here whether the bstp_nmix_* field /100 scaling assumption held, or what was fixed if not.] Sub-project 13 fully complete.
```

(Fill in the actual date and any field-name/scaling fix details when this step runs.)
