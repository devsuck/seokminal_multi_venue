# Design: IB Real-Time Trade Tick Streaming (Sub-project 3 of 5)

## Context

Sub-project 1 (KIS daily-bar batch ingestion) and sub-project 2 (KIS real-time
trade-tick streaming) are complete and merged to `main`. This sub-project mirrors
sub-project 2's shape for a second, independent venue:

1. ~~KIS data catalog ingestion~~ (done).
2. ~~KIS real-time trade tick streaming~~ (done).
3. **IB live data adapter** (this spec).
4. KIS + IB execution adapters.
5. Multi-venue strategy + backtest runner.

This sub-project builds a standalone Interactive Brokers client that streams
real-time trade ticks for a single instrument and prints mapped `TradeTick`
objects to the console. It does **not** wire into Nautilus's `LiveDataEngine` /
`TradingNode` yet, and does **not** include IB historical-bar ingestion — both
are deferred to later work, the same way sub-project 2 deferred them for KIS.

## Decisions made during brainstorming

- **Scope**: real-time trade ticks only, IB only. No historical-bar ingestion in
  this sub-project (IB's `reqHistoricalData` is a separate, unrelated API surface;
  the catalog-ingestion pattern is already proven via KIS sub-project 1 and isn't
  needed again here to validate the IB connection plumbing).
- **Library**: `ib_async` (the maintained fork/successor of the archived
  `ib_insync`; new dependency, added to `pyproject.toml`). Native `asyncio`
  support, consistent with the `websockets`-based async pattern used for KIS.
- **Connection target**: paper trading account via TWS/IB Gateway already running
  locally (`127.0.0.1:7497` default paper port — confirmed during implementation).
  No live-account risk; this sub-project only consumes market data.
- **Instrument**: `AAPL`, `SMART` exchange, `USD` (consistent in spirit with
  sub-project 2's single fixed instrument `005930`).
- **Tick type**: IB's `"AllLast"` tick-by-tick stream (regular-lot + odd-lot
  trades), the closest IB equivalent to KIS's 실시간체결 (all executed trades).
- **Output**: console print only, for verification — no `DataEngine`/`TradingNode`
  integration in this sub-project.

## Known risk: ib_async async/event integration unverified

`ib_async`'s tick-by-tick data arrives via the library's internal event system
(`Ticker.updateEvent` / `IB.pendingTickersEvent`), not as a plain `async for` over
a socket the way the `websockets` library exposes KIS's feed. The exact mechanics
of bridging that event-driven API into an `async def stream_trades(...) ->
AsyncIterator[...]` generator (matching the `KISWebSocketClient.stream_trades`
shape) are implemented here from documented library behavior, without having
run it against a live TWS connection at design time. Tasks must treat this
bridging code as **unverified until tested against a real paper-account
connection** — mirroring KIS sub-project 2's wire-format risk. The plan includes
a manual end-to-end verification task; if the event-to-iterator bridge doesn't
work as designed, that task fixes it. This is expected to require iteration, not
a sign the design is wrong.

## Architecture

```
nautilus-multi-venue/
  backends/ib/
    client.py         # IBClient.stream_trades(symbol) -> AsyncIterator[raw_tick]
  adapters/
    data_provider.py  # + build_us_equity(symbol) -> Equity
                       # + map_ib_trade_tick(raw_tick, instrument_id, price_precision, sequence) -> TradeTick
  live_trade_stream_ib.py  # entry point: connect, subscribe, map+print each tick
  tests/
    test_ib_client.py
    test_data_provider.py  # (extended with IB trade-tick mapping tests)
```

### `backends/ib/client.py`

- `IBClient(host: str = "127.0.0.1", port: int = 7497, client_id: int = 1)`: thin
  wrapper holding connection parameters and an `ib_async.IB` instance (or an
  injected fake for tests, matching the connection-object-injection pattern used
  by `KISWebSocketClient`).
- `async def stream_trades(self, symbol: str) -> AsyncIterator[TickByTickAllLast]`:
  connects via `await self._ib.connectAsync(self.host, self.port, self.client_id)`,
  builds a `Stock(symbol, "SMART", "USD")` contract, calls
  `self._ib.reqTickByTickData(contract, "AllLast")`, then bridges the library's
  tick events into an async generator — yielding each `TickByTickAllLast` object
  (carries `time`, `price`, `size`, `tickAttribLast` fields) as it arrives. Does
  not map to `TradeTick` — mapping is the data_provider's job, mirroring the
  KIS split between transport and parsing.
- No reconnect/backoff logic in this sub-project, same deferral as sub-project 2.

### `adapters/data_provider.py` (additions)

- `build_us_equity(symbol: str) -> Equity`: builds a Nautilus `Equity` instrument
  for a US-listed stock, `InstrumentId` of `f"{symbol}.NASDAQ"` (confirmed valid
  via `InstrumentId.from_str`; IB's order-routing destination is `SMART`, but the
  instrument's primary listing venue is `NASDAQ` for AAPL — the two are
  independent concepts, and only the instrument identifier matters here since
  this sub-project does no order routing), `USD` currency, price precision 2 —
  unlike KIS's whole-won precision 0. Mirrors `build_xkrx_equity`.
- `map_ib_trade_tick(raw_tick, instrument_id: InstrumentId, price_precision: int,
  sequence: int) -> TradeTick`: builds a Nautilus `TradeTick` from the IB tick
  object's `price`, `size`, and `time` (already a UTC-aware Python `datetime` —
  no KST-style manual timezone combination needed, unlike KIS). IB's tick-by-tick
  trade data does not include a buy/sell aggressor flag the way KIS's
  체결구분 code does, so `aggressor_side` is set to `AggressorSide.NO_AGGRESSOR`
  for all ticks (documented limitation, not a bug — IB's tick-by-tick API doesn't
  expose this without separately inferring it from quote-side data, which is out
  of scope). `trade_id` is built from `symbol + formatted time + sequence`,
  following the same per-process-sequence pattern as KIS (IB doesn't supply a
  trade ID either).

### `live_trade_stream_ib.py`

1. Build `Equity` instrument via `build_us_equity("AAPL")`.
2. Construct `IBClient()`, call `stream_trades("AAPL")`.
3. For each raw tick: `map_ib_trade_tick` → print the resulting `TradeTick`.
4. Runs until interrupted (Ctrl+C) or the connection drops.

## Error handling

- Connection failure (TWS not running, wrong port, paper-account mismatch) →
  raise immediately, no retry — same as KIS sub-project 2's approval-key
  failure handling.
- Tick objects with missing/unexpected fields → `map_ib_trade_tick` raises
  rather than silently producing a wrong `TradeTick`, matching the "fail loud"
  principle used for KIS's `parse_kis_trade_message`.
- No `.env` changes needed: TWS/Gateway socket connections don't use an API-key
  flow, only host/port/client-id, which are code-level defaults (not secrets).

## Testing

- `test_ib_client.py`: tests `stream_trades` against an injected fake `IB`-like
  object (matching the subset of `ib_async.IB`'s API surface actually used —
  `connectAsync`, `reqTickByTickData`, and the tick-event mechanism), confirming
  the contract built and the ticks yielded — same injection pattern as
  `test_ws_client.py`.
- `test_data_provider.py` additions: `build_us_equity` and `map_ib_trade_tick`
  tested against hand-constructed fake tick objects matching `ib_async`'s
  documented `TickByTickAllLast` shape — fixtures double as executable
  documentation of the assumed library behavior, so the manual verification task
  has a precise list of fields/behavior to confirm or correct.
- Manual end-to-end task (mirroring sub-project 2's Task 5): run
  `live_trade_stream_ib.py` against a real paper-account TWS connection during US
  market hours, confirm printed ticks have sane AAPL price/size values, and fix
  the event-to-iterator bridge or field mapping if real `ib_async` behavior
  disagrees with the documented assumption. US market hours are 09:30-16:00 ET
  (different from KIS's KST hours — the implementer must check ET, not KST,
  before running this task).

## Out of scope (deferred to later sub-projects)

- IB historical-bar ingestion into the `ParquetDataCatalog`.
- IB execution / order placement.
- Aggressor-side inference from quote data.
- Reconnect/backoff, multi-instrument subscription, live-account connection, and
  Nautilus `DataEngine`/`TradingNode` integration.
