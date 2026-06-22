# Design: IB Order Execution Adapter (Sub-project 5 of 6)

## Context

Sub-project 4 (KIS order execution adapter) is code-complete (2/3 tasks done,
blocked only on KRX market hours for manual verification — not a design
concern for this spec). This sub-project builds the IB-side counterpart, the
same way sub-project 3 mirrored sub-project 2 for real-time trade ticks:

1. ~~KIS data catalog ingestion~~ (done).
2. ~~KIS real-time trade tick streaming~~ (done).
3. IB real-time trade tick streaming (3/4 tasks done, blocked on IB
   market-data entitlements — unrelated to this spec; order placement does
   **not** require market-data entitlements, so this sub-project is not
   blocked by that issue).
4. KIS order execution adapter (2/3 tasks done, blocked on KRX market hours).
5. **IB order execution adapter** (this spec).
6. Multi-venue strategy + backtest runner.

This sub-project builds a standalone `ib_async`-based client that places,
queries, and cancels a stock order against IB's paper-trading account (the
same TWS paper connection sub-project 3 already uses, port 7497), and a
console script exercising the full place → query → cancel → query flow for a
single test order on `AAPL`. As with sub-project 4, this does **not** wire
into Nautilus's `ExecutionEngine`/`Order` types — those are deferred to
sub-project 6.

## End-goal alignment

The user's stated long-term goal for this repo is a Bloomberg-Terminal-style
platform (dashboard, multiple bots, agentic AI trading, quant research
tooling) sitting on top of this engine — not just a script pipeline (see
project memory `project-nautilus-platform-vision`). Concretely for this spec:
`IBOrderClient`'s three methods return plain, JSON-shaped dicts (`order_id`,
`status`, `filled`, `remaining`) rather than raw `ib_async.Trade`/`Order`
objects, mirroring `KISOrderClient`'s plain-dict return shape from
sub-project 4. Both venues' execution adapters now expose the same small,
serializable shape — this is exactly the kind of clean data boundary a future
dashboard backend would consume directly, without needing venue-specific
client library knowledge leaking past this layer.

## Decisions made during brainstorming

- **Scope**: IB only, mirroring sub-project 4's KIS-only scope. No shared
  code with `KISOrderClient` beyond the common "place/query/cancel, return
  plain dicts" shape — the underlying protocols (REST+TR-ID vs. TWS socket
  API) are unrelated.
- **Account**: the existing paper-trading TWS connection from sub-project 3
  (`127.0.0.1:7497`). Order placement does not require the market-data
  entitlements that blocked sub-project 3's Task 4 — confirmed via `ib_async`
  documentation (market data and order routing are separate IB permission
  systems), so this sub-project is not at risk of hitting that same blocker.
- **Instrument**: `AAPL` (consistent with sub-project 3, the existing US
  instrument in this codebase), quantity `1`.
- **Order types in scope**: both `MARKET` and `LIMIT`, same as sub-project
  4's KIS scope and for the same reason — a limit order below market lets the
  test order sit unfilled long enough to query and cancel it.
- **Operations in scope**: place, query, cancel — same three as sub-project 4.
  No order modification.
- **Output**: console print only, for verification. No Nautilus
  `ExecutionEngine`/`TradingNode`/`Order` integration in this sub-project.

## Known risk: async status propagation timing unverified

`ib_async`'s `IB.placeOrder()`/`IB.cancelOrder()` return immediately with a
`Trade` object, but the order's actual status (`Trade.orderStatus.status`,
e.g. `"PendingSubmit"` → `"Submitted"`) updates asynchronously as TWS sends
status messages back over the socket connection — driven by `ib_async`'s
internal event loop processing, the same way sub-project 3 found that tick
data arrives via `ticker.updateEvent`. This client's `place_order`/
`cancel_order` methods need to wait briefly (e.g. `await asyncio.sleep(...)`)
after calling into `ib_async` so the returned status dict reflects the
post-action state rather than a stale pre-update snapshot — but the exact
delay needed has not been verified against a live connection at design time.
This is the same category of risk sub-project 3 flagged for its event-bridge
code and sub-project 4 flagged for its TR IDs: the manual verification task
confirms the real timing and fixes the delay (or replaces polling with an
explicit wait-for-event approach) if a fixed sleep proves unreliable.

## Architecture

```
nautilus-multi-venue/
  backends/ib/
    order_client.py   # IBOrderClient.place_order/get_order_status/cancel_order
  place_test_order_ib.py  # entry point: place -> query -> cancel -> query, prints each step
  tests/
    test_ib_order_client.py
```

### `backends/ib/order_client.py`

- `IBOrderClient(host: str = "127.0.0.1", port: int = 7497, client_id: int =
  2, ib: IB | None = None)`: mirrors `backends/ib/client.py`'s `IBClient`
  constructor shape (host/port/client-id/injectable `ib` instance for
  testing). Defaults `client_id` to `2` (not `1`, the default already used by
  `IBClient` in sub-project 3) so a session can run both the data stream and
  the order client against the same TWS instance simultaneously without a
  client-ID collision — TWS requires distinct client IDs per concurrent API
  connection.
- `async def place_order(self, symbol: str, side: str, quantity: int,
  order_type: str, limit_price: float | None = None) -> dict`: calls a
  private `_ensure_connected()` helper (checks `self._ib.isConnected()`
  before calling `connectAsync` — calling `connectAsync` while already
  connected is unnecessary and this guard keeps `get_order_status`/
  `cancel_order` callable independently without reconnecting each time),
  builds a `Stock(symbol, "SMART", "USD")` contract,
  qualifies it via `qualifyContractsAsync` (same defensive step sub-project
  3's `IBClient` needed before `reqTickByTickData` — applied here
  preemptively rather than waiting to hit the same `conId` error again),
  builds an `ib_async.order.MarketOrder("BUY"|"SELL", quantity)` or
  `LimitOrder("BUY"|"SELL", quantity, limit_price)` depending on
  `order_type`, calls `self._ib.placeOrder(contract, order)` (returns a
  `Trade` synchronously), waits briefly for the status to settle, and
  returns `{"order_id": trade.order.orderId, "status":
  trade.orderStatus.status, "filled": trade.orderStatus.filled, "remaining":
  trade.orderStatus.remaining}`.
- `async def get_order_status(self, order_id: int) -> dict | None`: calls
  `_ensure_connected()` too (so it can be called on its own, e.g. from a
  later script run against the same paper session), then scans
  `self._ib.trades()` (the connection's full order history this session) for
  a `Trade` whose `trade.order.orderId == order_id`, and returns the same
  dict shape as `place_order`, or `None` if not found.
- `async def cancel_order(self, order_id: int) -> dict`: finds the matching
  `Trade` the same way `get_order_status` does (raises `ValueError` if not
  found — cancelling an order this client never placed/saw is a caller bug,
  not a legitimate "not found" case the way a status query's `None` is),
  calls `self._ib.cancelOrder(trade.order)`, waits briefly for the
  cancellation status to settle, and returns the updated status dict.
- No reconnect/backoff logic, no order modification — same deferrals as
  sub-project 4.

### `place_test_order_ib.py`

1. Construct `IBOrderClient()`.
2. Place a `LIMIT` `BUY` order for `AAPL`, quantity `1`, at a price below the
   current market price (read via `ib_async`'s market-data snapshot if
   available, or a hardcoded conservative low price if market-data
   entitlements are unavailable in this session — sub-project 3's experience
   shows market data may be unreliable on this account, so this script must
   not hard-depend on it the way sub-project 4's KIS script depends on
   `KISClient.get_daily_price`). Concretely: use a fixed limit price well
   below any plausible AAPL price (e.g. `$50`) rather than computing one from
   a live quote, so this script works regardless of sub-project 3's
   market-data blocker.
3. Print the placement response dict.
4. Call `get_order_status` for that order ID and print the result.
5. Call `cancel_order` for that order ID and print the result.
6. Call `get_order_status` again and print the result, to visually confirm
   `status` shows a cancelled state (e.g. `"Cancelled"` or `"ApiCancelled"` —
   exact value confirmed during manual verification).

## Error handling

- Connection failure → raise immediately, no retry (consistent with
  sub-projects 3-4).
- `cancel_order` called with an unknown `order_id` → `ValueError`, fails
  loud rather than silently no-op'ing.
- No special handling for IB's own order-rejection messages beyond what
  `Trade.orderStatus.status` naturally reflects (e.g. a status of
  `"Inactive"` or similar) — this is read directly off the object, not
  parsed from a side-channel error report, so there is no risk of silently
  swallowing a rejection.

## Testing

- `test_ib_order_client.py`: tests `place_order`, `get_order_status`, and
  `cancel_order` against an injected fake `IB`-like object (matching the
  subset of `ib_async.IB`'s API surface used — `connectAsync`,
  `qualifyContractsAsync`, `placeOrder`, `cancelOrder`, `trades`), following
  the same fake-injection pattern as `tests/test_ib_client.py` from
  sub-project 3.
- Manual end-to-end task (mirroring sub-project 4's Task 3): run
  `place_test_order_ib.py` against the real IB paper account during US
  market hours, confirm the full place → query → cancel → query flow
  behaves as expected, and fix the status-settling wait or field names if
  the real `ib_async` behavior disagrees with the documented assumption.

## Out of scope (deferred to later sub-projects)

- Order modification.
- Multiple concurrent orders, multi-instrument support, position/balance
  queries.
- Nautilus `ExecutionEngine`/`TradingNode`/`Order` integration.
