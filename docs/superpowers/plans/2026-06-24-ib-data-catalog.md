# IB Data Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull historical daily bars for `AAPL` from Interactive Brokers and
write them into the same local `ParquetDataCatalog` already used by
sub-project 1's KIS daily-bar data, mirroring sub-1's ingestion pattern
exactly so both venues' historical data live in one queryable catalog.

**Architecture:** Three small additions following sub-1's existing shape.
`backends/ib/client.py`'s `IBClient` gets a new `get_daily_bars` method that
calls `ib_async`'s `reqHistoricalDataAsync` (same connect/qualify pattern as
the existing `stream_trades` method). `adapters/data_provider.py` gets a new
`map_ib_daily_bar` function converting an `ib_async` `BarData` row into a
Nautilus `Bar`, reusing the already-existing `build_us_equity` and
`bar_type_for` helpers unchanged. A new entry-point script,
`data_ingestion_ib.py`, wires these together and writes into the existing
`./catalog` `ParquetDataCatalog` directory, mirroring `data_ingestion.py`'s
KIS flow.

**Tech Stack:** `ib_async` (already a dependency) — specifically `IB`,
`ib_async.contract.Stock`, `ib_async.objects.BarData`. `nautilus_trader`
(already a dependency) — `nautilus_trader.persistence.catalog.ParquetDataCatalog`,
`nautilus_trader.model.data.Bar`. `pytest`/`pytest-asyncio` (already
configured, `asyncio_mode = "auto"` — async test functions need no
decorator).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-24-ib-data-catalog-design.md`.
- Single instrument (`AAPL`, `SMART` exchange, `USD`), single bar size
  (`"1 day"`) — no other instruments or timeframes in this plan.
- Connects via the existing paper-port convention
  (`host="127.0.0.1"`, `port=7497`), matching every existing `IBClient`/
  `IBOrderClient` default in this repo. Do not introduce a port-7496 path.
- `whatToShow="TRADES"`, `useRTH=True` for the historical request.
- Writes into the same `./catalog` `ParquetDataCatalog` path already used
  by `data_ingestion.py`'s KIS data — no separate catalog directory.
- `get_daily_bars` raises `ValueError` (with symbol/range context) if IB's
  response is empty — never returns silently empty data.
- No chunking/pacing-sleep logic in this plan — single-call scope only (see
  spec's "Error Handling" section: chunking is deferred to a future
  sub-project if a multi-year backfill is ever needed).
- No changes to `condition_engine`, `strategy_spawner`, or any KIS-side
  code (`backends/kis/`, `data_ingestion.py`) in this plan.
- Verified directly against the installed libraries in this environment
  (not assumed from docs):
  - `IB.reqHistoricalDataAsync(self, contract, endDateTime, durationStr,
    barSizeSetting, whatToShow, useRTH, formatDate=1, keepUpToDate=False,
    chartOptions=[], timeout=60) -> BarDataList` — confirmed via
    `inspect.signature` against the installed `ib_async`.
  - `ib_async.objects.BarData(date, open, high, low, close, volume,
    average=0.0, barCount=0)` — confirmed via `inspect.signature`; `date`
    is a `datetime.date` for daily bars.

---

### Task 1: `IBClient.get_daily_bars`

**Files:**
- Modify: `backends/ib/client.py` (full file shown below)
- Test: `tests/test_ib_client.py` (extend `FakeIB`, add 2 new tests)

**Interfaces:**
- Consumes: nothing from other tasks (uses only the existing `IBClient`
  class and `ib_async`).
- Produces (consumed by Task 3): `IBClient.get_daily_bars(symbol: str,
  end_date: str, duration: str) -> list[BarData]` (async method). Raises
  `ValueError` if the response is empty.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `tests/test_ib_client.py` with:

```python
# tests/test_ib_client.py
import datetime as dt

import pytest
from ib_async.objects import BarData

from backends.ib.client import IBClient


class FakeTickByTick:
    def __init__(self, time, price, size):
        self.time = time
        self.price = price
        self.size = size


class FakeUpdateEvent:
    def __init__(self, ticker, batches):
        self._ticker = ticker
        self._batches = batches

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for batch in self._batches:
            self._ticker.tickByTicks = list(batch)
            yield self._ticker


class FakeTicker:
    def __init__(self, batches):
        self.tickByTicks: list = []
        self.updateEvent = FakeUpdateEvent(self, batches)


class FakeIB:
    def __init__(self, batches=None, historical_bars=None):
        self.connect_calls: list[tuple] = []
        self.qualify_calls: list[tuple] = []
        self.req_calls: list[tuple] = []
        self.historical_calls: list[tuple] = []
        self._ticker = FakeTicker(batches if batches is not None else [])
        self._historical_bars = historical_bars if historical_bars is not None else []

    async def connectAsync(self, host, port, client_id):
        self.connect_calls.append((host, port, client_id))

    async def qualifyContractsAsync(self, contract):
        self.qualify_calls.append((contract.symbol, contract.exchange, contract.currency))

    def reqTickByTickData(self, contract, tick_type):
        self.req_calls.append((contract.symbol, contract.exchange, contract.currency, tick_type))
        return self._ticker

    async def reqHistoricalDataAsync(
        self, contract, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH
    ):
        self.historical_calls.append(
            (
                contract.symbol,
                contract.exchange,
                contract.currency,
                endDateTime,
                durationStr,
                barSizeSetting,
                whatToShow,
                useRTH,
            )
        )
        return self._historical_bars


async def test_stream_trades_connects_subscribes_and_yields_ticks():
    tick1 = FakeTickByTick(dt.datetime(2024, 6, 3, 13, 30, 0, tzinfo=dt.timezone.utc), 195.50, 100)
    tick2 = FakeTickByTick(dt.datetime(2024, 6, 3, 13, 30, 1, tzinfo=dt.timezone.utc), 195.55, 50)
    fake_ib = FakeIB(batches=[[tick1], [tick2]])
    client = IBClient(host="127.0.0.1", port=7497, client_id=1, ib=fake_ib)

    received = []
    async for tick in client.stream_trades("AAPL"):
        received.append(tick)

    assert received == [tick1, tick2]
    assert fake_ib.connect_calls == [("127.0.0.1", 7497, 1)]
    assert fake_ib.qualify_calls == [("AAPL", "SMART", "USD")]
    assert fake_ib.req_calls == [("AAPL", "SMART", "USD", "AllLast")]


async def test_get_daily_bars_connects_subscribes_and_returns_bars():
    bar = BarData(date=dt.date(2024, 1, 2), open=185.5, high=186.5, low=184.0, close=186.0, volume=50000.0)
    fake_ib = FakeIB(historical_bars=[bar])
    client = IBClient(host="127.0.0.1", port=7497, client_id=1, ib=fake_ib)

    bars = await client.get_daily_bars("AAPL", end_date="20240601 23:59:59", duration="1 Y")

    assert bars == [bar]
    assert fake_ib.connect_calls == [("127.0.0.1", 7497, 1)]
    assert fake_ib.qualify_calls == [("AAPL", "SMART", "USD")]
    assert fake_ib.historical_calls == [
        ("AAPL", "SMART", "USD", "20240601 23:59:59", "1 Y", "1 day", "TRADES", True)
    ]


async def test_get_daily_bars_raises_value_error_on_empty_response():
    fake_ib = FakeIB(historical_bars=[])
    client = IBClient(host="127.0.0.1", port=7497, client_id=1, ib=fake_ib)

    with pytest.raises(ValueError, match="AAPL"):
        await client.get_daily_bars("AAPL", end_date="", duration="1 Y")
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/test_ib_client.py -v`
Expected: `test_stream_trades_connects_subscribes_and_yields_ticks` PASSES
(unchanged behavior); `test_get_daily_bars_connects_subscribes_and_returns_bars`
and `test_get_daily_bars_raises_value_error_on_empty_response` FAIL with
`AttributeError: 'IBClient' object has no attribute 'get_daily_bars'`.

- [ ] **Step 3: Implement `get_daily_bars`**

Replace the entire contents of `backends/ib/client.py` with:

```python
# backends/ib/client.py
from collections.abc import AsyncIterator

from ib_async import IB
from ib_async.contract import Stock
from ib_async.objects import BarData, TickByTickAllLast

TICK_TYPE = "AllLast"
DAILY_BAR_SIZE = "1 day"
DAILY_WHAT_TO_SHOW = "TRADES"


class IBClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        ib: IB | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib = ib if ib is not None else IB()

    async def stream_trades(self, symbol: str) -> AsyncIterator[TickByTickAllLast]:
        await self._ib.connectAsync(self._host, self._port, self._client_id)
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)
        ticker = self._ib.reqTickByTickData(contract, TICK_TYPE)
        async for _ in ticker.updateEvent:
            for tick in ticker.tickByTicks:
                yield tick
            ticker.tickByTicks.clear()

    async def get_daily_bars(self, symbol: str, end_date: str, duration: str) -> list[BarData]:
        await self._ib.connectAsync(self._host, self._port, self._client_id)
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_date,
            durationStr=duration,
            barSizeSetting=DAILY_BAR_SIZE,
            whatToShow=DAILY_WHAT_TO_SHOW,
            useRTH=True,
        )
        if not bars:
            raise ValueError(
                f"no historical daily bars returned for {symbol} "
                f"(end_date={end_date!r}, duration={duration!r}) -- "
                "check IB market data permissions"
            )
        return bars
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ib_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all existing tests still pass, plus the 2 new ones (no other
files reference `FakeIB`, so this is a safe, isolated change)

- [ ] **Step 6: Commit**

```bash
git add backends/ib/client.py tests/test_ib_client.py
git commit -m "feat: add IBClient.get_daily_bars for historical daily-bar ingestion"
```

---

### Task 2: `map_ib_daily_bar`

**Files:**
- Modify: `adapters/data_provider.py` (add import + one function, shown below)
- Modify: `tests/test_data_provider.py` (add import + one test, shown below)

**Interfaces:**
- Consumes: nothing from other tasks (pure mapping function, independent of
  Task 1).
- Produces (consumed by Task 3): `map_ib_daily_bar(row: BarData, bar_type:
  BarType, price_precision: int) -> Bar`.

- [ ] **Step 1: Write the failing test**

In `tests/test_data_provider.py`, change the import block at the top from:

```python
from adapters.data_provider import (
    bar_type_for,
    build_us_equity,
    build_xkrx_equity,
    map_ib_trade_tick,
    map_kis_daily_bar,
    map_kis_trade_tick,
    parse_kis_trade_message,
)
```

to:

```python
from adapters.data_provider import (
    bar_type_for,
    build_us_equity,
    build_xkrx_equity,
    map_ib_daily_bar,
    map_ib_trade_tick,
    map_kis_daily_bar,
    map_kis_trade_tick,
    parse_kis_trade_message,
)
```

Also add this import near the top of the file (alongside the other
top-of-file imports, after `from types import SimpleNamespace` if present,
otherwise after the `import datetime as dt` line):

```python
from ib_async.objects import BarData
```

Then add this test anywhere after `test_map_kis_daily_bar_converts_row_to_bar`:

```python
def test_map_ib_daily_bar_converts_row_to_bar():
    bar_type = bar_type_for(InstrumentId.from_str("AAPL.NASDAQ"))
    row = BarData(
        date=dt.date(2024, 1, 2),
        open=185.5,
        high=186.5,
        low=184.0,
        close=186.0,
        volume=50000.0,
    )

    bar = map_ib_daily_bar(row, bar_type, price_precision=2)

    assert bar.bar_type == bar_type
    assert bar.open.as_double() == 185.5
    assert bar.high.as_double() == 186.5
    assert bar.low.as_double() == 184.0
    assert bar.close.as_double() == 186.0
    assert bar.volume.as_double() == 50000.0
    # 2024-01-02 00:00:00 UTC in nanoseconds
    assert bar.ts_event == 1704153600000000000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_provider.py -v`
Expected: collection error / FAIL with
`ImportError: cannot import name 'map_ib_daily_bar' from 'adapters.data_provider'`

- [ ] **Step 3: Implement `map_ib_daily_bar`**

In `adapters/data_provider.py`, add this import alongside the existing
imports at the top of the file (after `from zoneinfo import ZoneInfo`,
before the `nautilus_trader` import group):

```python
from ib_async.objects import BarData
```

Then add this function anywhere after `map_ib_trade_tick`:

```python
def map_ib_daily_bar(row: BarData, bar_type: BarType, price_precision: int) -> Bar:
    event_date = dt.datetime.combine(row.date, dt.time.min, tzinfo=dt.timezone.utc)
    ts_event = dt_to_unix_nanos(event_date)

    return Bar(
        bar_type=bar_type,
        open=Price(float(row.open), price_precision),
        high=Price(float(row.high), price_precision),
        low=Price(float(row.low), price_precision),
        close=Price(float(row.close), price_precision),
        volume=Quantity(float(row.volume), 0),
        ts_event=ts_event,
        ts_init=ts_event,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_provider.py -v`
Expected: all tests pass, including the new
`test_map_ib_daily_bar_converts_row_to_bar`

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing suite + this task's 1 new test)

- [ ] **Step 6: Commit**

```bash
git add adapters/data_provider.py tests/test_data_provider.py
git commit -m "feat: add map_ib_daily_bar for IB historical bar conversion"
```

---

### Task 3: `data_ingestion_ib.py` entry point

**Files:**
- Create: `data_ingestion_ib.py`
- Test: `tests/test_data_ingestion_ib.py`

**Interfaces:**
- Consumes: `IBClient.get_daily_bars(symbol, end_date, duration) ->
  list[BarData]` (Task 1, async method); `map_ib_daily_bar(row, bar_type,
  price_precision) -> Bar` (Task 2); `build_us_equity(symbol) -> Equity`
  and `bar_type_for(instrument_id) -> BarType` (already existing, used
  unchanged).
- Produces: `run_ingestion_ib(symbol: str, end_date: str, duration: str,
  catalog_path: str, client: IBClient) -> int` (async function, returns
  bar count written). No other task in this plan depends on this.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_ingestion_ib.py
import datetime as dt
import tempfile
from unittest.mock import AsyncMock

from ib_async.objects import BarData
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from data_ingestion_ib import run_ingestion_ib


async def test_run_ingestion_ib_writes_instrument_and_bars_to_catalog():
    client = AsyncMock()
    client.get_daily_bars.return_value = [
        BarData(date=dt.date(2024, 1, 2), open=185.5, high=186.5, low=184.0, close=186.0, volume=50000.0),
        BarData(date=dt.date(2024, 1, 3), open=186.0, high=187.0, low=185.0, close=186.8, volume=42000.0),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        written = await run_ingestion_ib(
            symbol="AAPL",
            end_date="20240103 23:59:59",
            duration="1 Y",
            catalog_path=tmp_dir,
            client=client,
        )

        assert written == 2

        catalog = ParquetDataCatalog(tmp_dir)
        instruments = catalog.instruments()
        assert len(instruments) == 1
        assert str(instruments[0].id) == "AAPL.NASDAQ"

        bars = catalog.bars()
        assert len(bars) == 2
        assert bars[0].close.as_double() == 186.0
        assert bars[1].close.as_double() == 186.8

    client.get_daily_bars.assert_called_once_with("AAPL", "20240103 23:59:59", "1 Y")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_ingestion_ib.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_ingestion_ib'`

- [ ] **Step 3: Implement `data_ingestion_ib.py`**

```python
# data_ingestion_ib.py
import argparse
import asyncio
import datetime as dt

from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for, build_us_equity, map_ib_daily_bar
from backends.ib.client import IBClient


async def run_ingestion_ib(
    symbol: str, end_date: str, duration: str, catalog_path: str, client: IBClient
) -> int:
    instrument = build_us_equity(symbol)
    bar_type = bar_type_for(instrument.id)

    rows = await client.get_daily_bars(symbol, end_date, duration)
    bars = [map_ib_daily_bar(row, bar_type, instrument.price_precision) for row in rows]

    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([instrument])
    catalog.write_data(bars)

    return len(bars)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest IB daily bars into a ParquetDataCatalog")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--end-date", default=dt.date.today().strftime("%Y%m%d 23:59:59"))
    parser.add_argument("--duration", default="1 Y")
    parser.add_argument("--catalog-path", default="./catalog")
    args = parser.parse_args()

    client = IBClient()

    written = asyncio.run(
        run_ingestion_ib(args.symbol, args.end_date, args.duration, args.catalog_path, client)
    )
    print(
        f"Wrote {written} bars for {args.symbol} "
        f"(duration={args.duration}, end={args.end_date}) to {args.catalog_path}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_ingestion_ib.py -v`
Expected: 1 passed

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing suite + this plan's 4 new tests across
all 3 tasks: 2 in `test_ib_client.py`, 1 in `test_data_provider.py`, 1 in
`test_data_ingestion_ib.py`)

- [ ] **Step 6: Commit**

```bash
git add data_ingestion_ib.py tests/test_data_ingestion_ib.py
git commit -m "feat: add data_ingestion_ib.py entry point for IB historical bars"
```

---

### Task 4: Update progress ledger and dispatch final review

**Files:** none (bookkeeping only)

- [ ] **Step 1: Append to the progress ledger**

Append to `.superpowers/sdd/progress.md`:

```
--- Sub-project 8: IB data catalog (spec 8fd5c0a, plan <this commit>) ---
Task 1: complete (backends/ib/client.py get_daily_bars, commit <hash>)
Task 2: complete (adapters/data_provider.py map_ib_daily_bar, commit <hash>)
Task 3: complete (data_ingestion_ib.py, commit <hash>)
```

- [ ] **Step 2: Dispatch the final whole-branch review**

Per `superpowers:subagent-driven-development`'s process: use the commit
right before Task 1 (the spec commit, `8fd5c0a`) as the base. Run
`scripts/review-package 8fd5c0a HEAD` (from the `subagent-driven-development`
skill's directory) as the diff package, dispatch a code-reviewer subagent on
the most capable available model per that skill's `code-reviewer.md`
template, and resolve any Critical/Important findings before considering
sub-project 8 complete.

- [ ] **Step 3: Manual end-to-end verification (not automated)**

With a paper-TWS instance running locally (`127.0.0.1:7497`), run:

```bash
python3 data_ingestion_ib.py
```

Confirm it prints a non-zero bar count, then inspect the catalog (e.g.
`ParquetDataCatalog("./catalog").bars()`) to confirm AAPL daily bars are
present alongside the existing KIS `005930.XKRX` data. If IB returns an
empty response (permissions issue), do not guess at a workaround —
escalate to the user per the spec's "Open Questions / Risks" section.

## Out of scope (reminder, per spec)

Do not add: additional instruments or bar sizes/timeframes, backtest run
orchestration or performance reporting (Sharpe/MDD — sub-project 9), any
change to `condition_engine`/`strategy_spawner`, any change to the KIS-side
ingestion code, or a real-account (port 7496) connection. These belong to
sub-project 9 or later.
