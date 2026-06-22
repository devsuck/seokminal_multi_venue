# IB Real-Time Trade Tick Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream real-time trade ticks for `AAPL` from Interactive Brokers (paper
account, via TWS/IB Gateway) and print mapped Nautilus `TradeTick` objects to the
console, mirroring the shape of sub-project 2's KIS real-time streaming.

**Architecture:** A thin `IBClient` wraps `ib_async.IB`'s tick-by-tick API behind
an `async def stream_trades(symbol) -> AsyncIterator[TickByTickAllLast]`
generator. `adapters/data_provider.py` gains pure mapping functions
(`build_us_equity`, `map_ib_trade_tick`) with no IB-connection dependency, kept
separate and unit-testable. `live_trade_stream_ib.py` wires client → mapper →
console print, mirroring `live_trade_stream.py`.

**Tech Stack:** `ib_async` 2.1.0 (installed and inspected directly — see Global
Constraints), `nautilus_trader`, `pytest`/`pytest-asyncio` (already configured
with `asyncio_mode = "auto"`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-22-ib-realtime-trades-design.md`.
- Instrument: `AAPL`, `InstrumentId` of `AAPL.NASDAQ`, `USD` currency, price
  precision `2`, price increment `0.01`, lot size `1` (per spec's
  `build_us_equity`).
- Connection: paper account via TWS/IB Gateway already running locally, default
  host `127.0.0.1`, default port `7497`, default `client_id` `1`.
- Tick type: `ib_async`'s `"AllLast"` tick-by-tick stream (regular + odd-lot
  trades). `aggressor_side` is always `AggressorSide.NO_AGGRESSOR` — IB's
  tick-by-tick API does not expose a buy/sell flag; this is a documented
  limitation per spec, not a bug to fix.
- No reconnect/backoff logic. No `DataEngine`/`TradingNode` integration. No
  historical-bar ingestion. All deferred per spec's "Out of scope" section.
- `ib_async`'s real API was inspected directly (version 2.1.0, installed in this
  environment) rather than assumed from documentation, removing the
  documentation-only risk the spec flagged for the event-to-iterator bridge:
  - `IB.connectAsync(host: str = "127.0.0.1", port: int = 7497, clientId: int = 1, ...)`
    is a coroutine.
  - `IB.reqTickByTickData(contract: Contract, tickType: str, numberOfTicks: int = 0, ignoreSize: bool = False) -> Ticker`
    is synchronous and returns a `Ticker` immediately (subscription request).
  - `Ticker.tickByTicks: list[TickByTickAllLast | ...]` holds newly arrived ticks.
  - `Ticker.updateEvent` is an `eventkit.Event`, and `eventkit.Event` implements
    `__aiter__` — so `async for _ in ticker.updateEvent:` is valid and fires once
    per ticker update (after which `ticker.tickByTicks` holds the new ticks).
  - `TickByTickAllLast` exposes `.time` (UTC-aware `datetime.datetime`), `.price`
    (`float`), `.size` (`float`) as plain attributes.
  - `Stock(symbol: str, exchange: str, currency: str)` constructs a contract,
    e.g. `Stock("AAPL", "SMART", "USD")`.

---

### Task 1: IB client with tick-by-tick streaming

**Files:**
- Create: `backends/ib/__init__.py` (empty, package marker — mirrors `backends/kis/__init__.py`)
- Create: `backends/ib/client.py`
- Test: `tests/test_ib_client.py`
- Modify: `pyproject.toml` — add `"ib_async>=2.1.0"` to `dependencies`

**Interfaces:**
- Consumes: `ib_async.IB`, `ib_async.contract.Stock`, `ib_async.objects.TickByTickAllLast`.
- Produces: `IBClient(host: str = "127.0.0.1", port: int = 7497, client_id: int = 1, ib: IB | None = None)`
  with `async def stream_trades(self, symbol: str) -> AsyncIterator[TickByTickAllLast]`.
  Task 3 consumes this exact signature.

- [ ] **Step 1: Add the `ib_async` dependency**

Edit `pyproject.toml`'s `dependencies` list to read:

```toml
dependencies = [
    "nautilus_trader",
    "requests>=2.31",
    "python-dotenv>=1.0",
    "ib_async>=2.1.0",
]
```

Run: `python3 -m pip install ib_async`
Expected: installs cleanly (already verified working in this environment;
installs `aeventkit`, `nest_asyncio`, `tzdata` as transitive deps).

- [ ] **Step 2: Write the failing test**

```python
# tests/test_ib_client.py
import datetime as dt

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
    def __init__(self, batches):
        self.connect_calls: list[tuple] = []
        self.req_calls: list[tuple] = []
        self._ticker = FakeTicker(batches)

    async def connectAsync(self, host, port, client_id):
        self.connect_calls.append((host, port, client_id))

    def reqTickByTickData(self, contract, tick_type):
        self.req_calls.append((contract.symbol, contract.exchange, contract.currency, tick_type))
        return self._ticker


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
    assert fake_ib.req_calls == [("AAPL", "SMART", "USD", "AllLast")]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_ib_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backends.ib'`

- [ ] **Step 4: Implement `backends/ib/__init__.py` and `backends/ib/client.py`**

```python
# backends/ib/__init__.py
```

```python
# backends/ib/client.py
from collections.abc import AsyncIterator

from ib_async import IB
from ib_async.contract import Stock
from ib_async.objects import TickByTickAllLast

TICK_TYPE = "AllLast"


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
        ticker = self._ib.reqTickByTickData(contract, TICK_TYPE)
        async for _ in ticker.updateEvent:
            for tick in ticker.tickByTicks:
                yield tick
            ticker.tickByTicks.clear()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_ib_client.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add backends/ib/__init__.py backends/ib/client.py tests/test_ib_client.py pyproject.toml
git commit -m "feat: add IB tick-by-tick streaming client"
```

---

### Task 2: Map IB ticks to Nautilus instrument and TradeTick

**Files:**
- Modify: `adapters/data_provider.py` (add new functions; existing KIS functions
  untouched)
- Test: `tests/test_data_provider.py` (add new test functions; existing tests
  untouched)

**Interfaces:**
- Consumes: `TickByTickAllLast` objects (or any object with `.time`
  (UTC-aware `datetime.datetime`), `.price` (`float`), `.size` (`float`)
  attributes) from Task 1's `IBClient.stream_trades`.
- Produces: `build_us_equity(symbol: str) -> Equity`,
  `map_ib_trade_tick(raw_tick, instrument_id: InstrumentId, price_precision: int, sequence: int) -> TradeTick`.
  Task 3 consumes both exact signatures.

- [ ] **Step 1: Write the failing tests**

Add to the top of `tests/test_data_provider.py`, alongside the existing imports:

```python
from adapters.data_provider import build_us_equity, map_ib_trade_tick
```

Append to `tests/test_data_provider.py`:

```python
def test_build_us_equity_has_expected_fields():
    equity = build_us_equity("AAPL")

    assert equity.id == InstrumentId.from_str("AAPL.NASDAQ")
    assert str(equity.quote_currency) == "USD"
    assert equity.price_precision == 2
    assert equity.lot_size.as_double() == 1.0


def test_map_ib_trade_tick_converts_raw_tick_to_trade_tick():
    instrument_id = InstrumentId.from_str("AAPL.NASDAQ")
    raw_tick = SimpleNamespace(
        time=dt.datetime(2024, 6, 3, 13, 30, 0, tzinfo=dt.timezone.utc),
        price=195.50,
        size=100,
    )

    tick = map_ib_trade_tick(raw_tick, instrument_id, price_precision=2, sequence=3)

    assert tick.instrument_id == instrument_id
    assert tick.price.as_double() == 195.50
    assert tick.size.as_double() == 100.0
    assert tick.aggressor_side == AggressorSide.NO_AGGRESSOR
    assert str(tick.trade_id) == "AAPL-20240603133000-3"
    assert tick.ts_event == 1717421400000000000  # 2024-06-03 13:30:00 UTC -> ns
```

`tests/test_data_provider.py` must also import `SimpleNamespace` — add
`from types import SimpleNamespace` to its imports (alongside the existing
`import datetime as dt`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_data_provider.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_us_equity'`

- [ ] **Step 3: Implement in `adapters/data_provider.py`**

Add `USD` to the existing `nautilus_trader.model.currencies` import line:

```python
from nautilus_trader.model.currencies import KRW, USD
```

Append to `adapters/data_provider.py`:

```python
def build_us_equity(symbol: str) -> Equity:
    now_ns = dt_to_unix_nanos(dt.datetime.now(dt.timezone.utc))
    return Equity(
        instrument_id=InstrumentId.from_str(f"{symbol}.NASDAQ"),
        raw_symbol=Symbol(symbol),
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=now_ns,
        ts_init=now_ns,
    )


def map_ib_trade_tick(
    raw_tick,
    instrument_id: InstrumentId,
    price_precision: int,
    sequence: int,
) -> TradeTick:
    ts_event = dt_to_unix_nanos(raw_tick.time)
    time_str = raw_tick.time.strftime("%Y%m%d%H%M%S")

    return TradeTick(
        instrument_id=instrument_id,
        price=Price(float(raw_tick.price), price_precision),
        size=Quantity(float(raw_tick.size), 0),
        aggressor_side=AggressorSide.NO_AGGRESSOR,
        trade_id=TradeId(f"{instrument_id.symbol}-{time_str}-{sequence}"),
        ts_event=ts_event,
        ts_init=ts_event,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_provider.py -v`
Expected: all passed (existing KIS tests + 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add adapters/data_provider.py tests/test_data_provider.py
git commit -m "feat: map IB trade ticks to Nautilus instrument and TradeTick"
```

---

### Task 3: Live IB trade-stream entry script

**Files:**
- Create: `live_trade_stream_ib.py`
- Test: `tests/test_live_trade_stream_ib.py`

**Interfaces:**
- Consumes: `IBClient.stream_trades(symbol) -> AsyncIterator[TickByTickAllLast]`
  (Task 1), `build_us_equity(symbol) -> Equity`, `map_ib_trade_tick(raw_tick, instrument_id, price_precision, sequence) -> TradeTick` (Task 2).
- Produces: `run_stream(symbol: str, client: IBClient, instrument_id: InstrumentId, price_precision: int, print_fn=print) -> None` and `main() -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_live_trade_stream_ib.py
import datetime as dt

from nautilus_trader.model.identifiers import InstrumentId

from live_trade_stream_ib import run_stream


class FakeRawTick:
    def __init__(self, time, price, size):
        self.time = time
        self.price = price
        self.size = size


class FakeIBClient:
    def __init__(self, ticks: list) -> None:
        self._ticks = ticks

    async def stream_trades(self, symbol: str):
        for tick in self._ticks:
            yield tick


async def test_run_stream_prints_mapped_ticks():
    ticks = [
        FakeRawTick(dt.datetime(2024, 6, 3, 13, 30, 0, tzinfo=dt.timezone.utc), 195.50, 100),
        FakeRawTick(dt.datetime(2024, 6, 3, 13, 30, 1, tzinfo=dt.timezone.utc), 195.55, 50),
    ]
    client = FakeIBClient(ticks)
    instrument_id = InstrumentId.from_str("AAPL.NASDAQ")
    printed = []

    await run_stream(
        symbol="AAPL",
        client=client,
        instrument_id=instrument_id,
        price_precision=2,
        print_fn=printed.append,
    )

    assert len(printed) == 2
    assert printed[0].price.as_double() == 195.50
    assert printed[1].price.as_double() == 195.55
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_live_trade_stream_ib.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'live_trade_stream_ib'`

- [ ] **Step 3: Implement `live_trade_stream_ib.py`**

```python
# live_trade_stream_ib.py
import asyncio

from nautilus_trader.model.identifiers import InstrumentId

from adapters.data_provider import build_us_equity, map_ib_trade_tick
from backends.ib.client import IBClient


async def run_stream(
    symbol: str,
    client: IBClient,
    instrument_id: InstrumentId,
    price_precision: int,
    print_fn=print,
) -> None:
    sequence = 0
    async for raw_tick in client.stream_trades(symbol):
        sequence += 1
        tick = map_ib_trade_tick(raw_tick, instrument_id, price_precision, sequence)
        print_fn(tick)


def main() -> None:
    symbol = "AAPL"
    equity = build_us_equity(symbol)
    client = IBClient()

    asyncio.run(
        run_stream(
            symbol=symbol,
            client=client,
            instrument_id=equity.id,
            price_precision=equity.price_precision,
        )
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_live_trade_stream_ib.py -v`
Expected: 1 passed

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: all tests passed (23 existing + new ones from Tasks 1-3)

- [ ] **Step 6: Commit**

```bash
git add live_trade_stream_ib.py tests/test_live_trade_stream_ib.py
git commit -m "feat: add live IB trade-tick stream entry script"
```

---

### Task 4: Manual end-to-end verification against the real IB paper feed

**Files:** none (manual verification step, no code changes — except a fix to
the event-to-iterator bridge or field mapping, described in Step 3, if the real
`ib_async` behavior disagrees with what Task 1's Global Constraints section
verified by reading the installed library's source)

**Interfaces:**
- Consumes: `main()` from `live_trade_stream_ib.py` (Task 3), a running TWS or
  IB Gateway connected to a paper account, listening on `127.0.0.1:7497`.

- [ ] **Step 1: Confirm preconditions, then run the script during US market hours**

Confirm: it is a US trading weekday, between 09:30 and 16:00 **US Eastern
Time** (not KST — convert carefully), and TWS/IB Gateway is running and logged
into a paper account with API connections enabled on port 7497.

Run: `python3 live_trade_stream_ib.py`
Expected: connects, subscribes, and prints a stream of `TradeTick` objects as
`AAPL` trades occur. If the market is closed or TWS isn't running, this will
hang or raise a connection error — that's expected, not a bug; re-run once both
conditions are met.

- [ ] **Step 2: Sanity-check the printed ticks**

Confirm: `price` values are in a plausible range for Apple Inc. (roughly $150-300
depending on when this runs), `size` values are plausible share counts, and
`aggressor_side` is `NO_AGGRESSOR` for every tick (expected — documented
limitation, not a bug to fix here).

- [ ] **Step 3: Fix the event bridge or field mapping if the real feed disagrees**

If the script raises an unexpected error from `ib_async` (e.g. `updateEvent`
doesn't behave as `async for` expects, or `tickByTicks` isn't populated as
described), capture the actual exception/behavior, adjust `backends/ib/client.py`
accordingly, update `tests/test_ib_client.py` to match the corrected behavior,
re-run `pytest -v` to confirm everything still passes, and commit:

```bash
git add backends/ib/client.py tests/test_ib_client.py
git commit -m "fix: correct IB tick-by-tick event bridging against live feed"
```

If the behavior already matches (no fix needed), skip the commit — this task
ends with just the manual confirmation in Step 2.

- [ ] **Step 4: Update the progress ledger**

Append to `.superpowers/sdd/progress.md`:
`Task 4: complete (manual verification, real IB paper account, <what you observed>)`

- [ ] **Step 5: Dispatch the final whole-branch review**

Per `superpowers:subagent-driven-development`'s process: everything is linear
on `main`, so use the commit before Task 1 as the base. Run
`scripts/review-package <task-1-base-sha> HEAD` (from the
`subagent-driven-development` skill's directory) as the diff package, dispatch
a code-reviewer subagent on the most capable available model per that skill's
`code-reviewer.md` template, and resolve any Critical/Important findings before
considering sub-project 3 complete.

## Out of scope (reminder, per spec)

Do not add: IB historical-bar ingestion, IB execution/order placement,
aggressor-side inference, reconnect/backoff, multi-instrument subscription,
live-account connection, or any Nautilus `DataEngine`/`TradingNode` integration.
These belong to later sub-projects.
