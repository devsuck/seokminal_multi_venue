# IB Order Execution Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place, query, and cancel a stock order against IB's paper-trading
account for `AAPL`, and prove the full place → query → cancel → query flow
works end to end via a console script.

**Architecture:** `IBOrderClient` (mirroring sub-project 3's `IBClient`
constructor shape: host/port/client-id/injectable `ib` instance) wraps
`ib_async`'s `placeOrder`/`cancelOrder`/`trades()`, returning plain dicts
(`order_id`, `status`, `filled`, `remaining`) — the same shape
`KISOrderClient` returns for KIS, so both venues' execution adapters share one
small, serializable contract. `place_test_order_ib.py` wires it together:
place a limit buy below market, query it, cancel it, query it again.

**Tech Stack:** `ib_async>=2.1.0` (already a dependency, added in
sub-project 3), `pytest`/`pytest-asyncio` (already configured).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-23-ib-order-execution-design.md`.
- Connection: paper account via the same TWS/IB Gateway instance sub-project
  3 uses, host `127.0.0.1`, port `7497`. **Client ID `2`** (not `1`, which
  `IBClient` from sub-project 3 already defaults to — TWS requires distinct
  client IDs per concurrent API connection, and both clients may run in the
  same session).
- Instrument/size: `AAPL`, quantity `1` (fixed).
- Order types: `"MARKET"` and `"LIMIT"`.
- Return shape (verified against the installed `ib_async` 2.1.0 source — see
  below): `{"order_id": int, "status": str, "filled": float, "remaining":
  float}` from all three methods (`get_order_status` returns this dict or
  `None`).
- No reconnect/backoff. No order modification. No
  `DataEngine`/`ExecutionEngine`/`TradingNode`/`Order` integration. All
  deferred per spec's "Out of scope" section.
- `ib_async`'s real API was inspected directly (version 2.1.0, installed in
  this environment) rather than assumed from documentation:
  - `IB.placeOrder(contract: Contract, order: Order) -> Trade` is
    synchronous. If `order.orderId` is `0` (the default for a freshly
    constructed `Order`/`MarketOrder`/`LimitOrder`), `placeOrder` assigns a
    real ID internally (`order.orderId = self.client.getReqId()`) before
    returning — so the trade returned by `placeOrder` always has a non-zero
    `trade.order.orderId` to use as this client's `order_id`.
  - `IB.cancelOrder(order: Order, manualCancelOrderTime: str = "") -> Trade |
    None` is synchronous; returns `None` and logs an error (does not raise)
    if `order.orderId` isn't found in `ib.wrapper.trades` — this plan's
    `cancel_order` must check for `None` itself and raise `ValueError`, since
    `ib_async` won't.
  - `IB.trades() -> list[Trade]` returns every `Trade` from the session
    (`list(self.wrapper.trades.values())`), each with `.order.orderId` and
    `.orderStatus.status`/`.filled`/`.remaining` (all live-mutated in place
    by `ib_async`'s background event processing — no separate poll/refresh
    call exists or is needed; reading the attributes again after an
    `asyncio.sleep` picks up whatever has arrived by then).
  - `MarketOrder(action: str, totalQuantity: float, **kwargs)` and
    `LimitOrder(action: str, totalQuantity: float, lmtPrice: float,
    **kwargs)` from `ib_async.order`; `action` is `"BUY"` or `"SELL"`. A
    freshly constructed `MarketOrder`'s `.lmtPrice` is **not** `None` — it's
    `ib_async.order.UNSET_DOUBLE` (`1.7976931348623157e+308`, IB's
    sentinel for "no price set"). Tests asserting on a placed market order's
    `lmtPrice` must compare against `UNSET_DOUBLE`, not `None` (verified by
    constructing a real `MarketOrder` against the installed library).
  - `OrderStatus.Cancelled == "Cancelled"`,
    `OrderStatus.DoneStates == frozenset({"Filled", "ApiCancelled",
    "Cancelled", "Inactive"})` — useful reference values for Task 3's manual
    verification, not asserted on directly by this plan's unit tests (the
    fakes control their own status strings).
  - `Stock(symbol: str, exchange: str, currency: str)` and
    `IB.qualifyContractsAsync(*contracts) -> list[Contract | ...]` — same
    pattern sub-project 3's `IBClient` already uses for `reqTickByTickData`.
  - `IB.isConnected() -> bool` — used to avoid reconnecting on every call.

---

### Task 1: `IBOrderClient` — place, query, cancel

**Files:**
- Create: `backends/ib/order_client.py`
- Test: `tests/test_ib_order_client.py`

**Interfaces:**
- Consumes: `ib_async.IB`, `ib_async.contract.Stock`,
  `ib_async.order.MarketOrder`/`LimitOrder`.
- Produces:
  - `IBOrderClient(host: str = "127.0.0.1", port: int = 7497, client_id: int = 2, ib: IB | None = None)`
  - `async def place_order(self, symbol: str, side: str, quantity: int, order_type: str, limit_price: float | None = None) -> dict`
  - `async def get_order_status(self, order_id: int) -> dict | None`
  - `async def cancel_order(self, order_id: int) -> dict`

  Task 2 consumes all three exact signatures.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ib_order_client.py
from ib_async.order import UNSET_DOUBLE

from backends.ib.order_client import IBOrderClient


class FakeOrder:
    def __init__(self, action, totalQuantity, lmtPrice=None):
        self.action = action
        self.totalQuantity = totalQuantity
        self.lmtPrice = lmtPrice
        self.orderId = 0
        self.clientId = 0
        self.permId = 0


class FakeOrderStatus:
    def __init__(self, status="PendingSubmit", filled=0.0, remaining=0.0):
        self.status = status
        self.filled = filled
        self.remaining = remaining


class FakeTrade:
    def __init__(self, order, status="PendingSubmit", filled=0.0, remaining=0.0):
        self.order = order
        self.orderStatus = FakeOrderStatus(status, filled, remaining)


class FakeIB:
    def __init__(self):
        self.connect_calls: list[tuple] = []
        self.qualify_calls: list[tuple] = []
        self.placed_orders: list = []
        self.cancelled_orders: list = []
        self._connected = False
        self._next_order_id = 100
        self._trades: list[FakeTrade] = []

    def isConnected(self) -> bool:
        return self._connected

    async def connectAsync(self, host, port, client_id):
        self.connect_calls.append((host, port, client_id))
        self._connected = True

    async def qualifyContractsAsync(self, contract):
        self.qualify_calls.append((contract.symbol, contract.exchange, contract.currency))

    def placeOrder(self, contract, order):
        order.orderId = self._next_order_id
        self._next_order_id += 1
        self.placed_orders.append((contract.symbol, order.action, order.totalQuantity, order.lmtPrice))
        trade = FakeTrade(order, status="PendingSubmit", filled=0.0, remaining=order.totalQuantity)
        self._trades.append(trade)
        return trade

    def cancelOrder(self, order):
        self.cancelled_orders.append(order.orderId)
        for trade in self._trades:
            if trade.order.orderId == order.orderId:
                trade.orderStatus.status = "Cancelled"
                return trade
        return None

    def trades(self):
        return list(self._trades)


def _client(ib):
    return IBOrderClient(host="127.0.0.1", port=7497, client_id=2, ib=ib)


async def test_place_order_market_buy_connects_qualifies_and_returns_status_dict():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    result = await client.place_order(symbol="AAPL", side="BUY", quantity=1, order_type="MARKET")

    assert fake_ib.connect_calls == [("127.0.0.1", 7497, 2)]
    assert fake_ib.qualify_calls == [("AAPL", "SMART", "USD")]
    assert fake_ib.placed_orders == [("AAPL", "BUY", 1, UNSET_DOUBLE)]
    assert result["order_id"] == 100
    assert result["status"] == "PendingSubmit"
    assert result["filled"] == 0.0
    assert result["remaining"] == 1


async def test_place_order_limit_sell_passes_limit_price():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    await client.place_order(symbol="AAPL", side="SELL", quantity=1, order_type="LIMIT", limit_price=50.0)

    assert fake_ib.placed_orders == [("AAPL", "SELL", 1, 50.0)]


async def test_place_order_does_not_reconnect_if_already_connected():
    fake_ib = FakeIB()
    fake_ib._connected = True
    client = _client(fake_ib)

    await client.place_order(symbol="AAPL", side="BUY", quantity=1, order_type="MARKET")

    assert fake_ib.connect_calls == []


async def test_get_order_status_returns_matching_trade_as_dict():
    fake_ib = FakeIB()
    client = _client(fake_ib)
    await client.place_order(symbol="AAPL", side="BUY", quantity=1, order_type="MARKET")

    result = await client.get_order_status(order_id=100)

    assert result == {"order_id": 100, "status": "PendingSubmit", "filled": 0.0, "remaining": 1}


async def test_get_order_status_returns_none_when_not_found():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    result = await client.get_order_status(order_id=999)

    assert result is None


async def test_cancel_order_cancels_matching_trade_and_returns_updated_status():
    fake_ib = FakeIB()
    client = _client(fake_ib)
    await client.place_order(symbol="AAPL", side="BUY", quantity=1, order_type="MARKET")

    result = await client.cancel_order(order_id=100)

    assert fake_ib.cancelled_orders == [100]
    assert result["status"] == "Cancelled"


async def test_cancel_order_raises_value_error_when_not_found():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    try:
        await client.cancel_order(order_id=999)
        assert False, "expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ib_order_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backends.ib.order_client'`

- [ ] **Step 3: Implement `backends/ib/order_client.py`**

```python
# backends/ib/order_client.py
from ib_async import IB
from ib_async.contract import Stock
from ib_async.order import LimitOrder, MarketOrder, Trade


class IBOrderClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 2,
        ib: IB | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib = ib if ib is not None else IB()

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: float | None = None,
    ) -> dict:
        await self._ensure_connected()
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)

        if order_type == "LIMIT":
            order = LimitOrder(side, quantity, limit_price)
        else:
            order = MarketOrder(side, quantity)

        trade = self._ib.placeOrder(contract, order)
        return self._to_dict(trade)

    async def get_order_status(self, order_id: int) -> dict | None:
        await self._ensure_connected()
        trade = self._find_trade(order_id)
        if trade is None:
            return None
        return self._to_dict(trade)

    async def cancel_order(self, order_id: int) -> dict:
        await self._ensure_connected()
        trade = self._find_trade(order_id)
        if trade is None:
            raise ValueError(f"no known order with order_id={order_id}")

        cancelled = self._ib.cancelOrder(trade.order)
        if cancelled is None:
            raise ValueError(f"no known order with order_id={order_id}")
        return self._to_dict(cancelled)

    async def _ensure_connected(self) -> None:
        if not self._ib.isConnected():
            await self._ib.connectAsync(self._host, self._port, self._client_id)

    def _find_trade(self, order_id: int) -> Trade | None:
        for trade in self._ib.trades():
            if trade.order.orderId == order_id:
                return trade
        return None

    @staticmethod
    def _to_dict(trade: Trade) -> dict:
        return {
            "order_id": trade.order.orderId,
            "status": trade.orderStatus.status,
            "filled": trade.orderStatus.filled,
            "remaining": trade.orderStatus.remaining,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ib_order_client.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backends/ib/order_client.py tests/test_ib_order_client.py
git commit -m "feat: add IB paper-trading order place/query/cancel client"
```

---

### Task 2: `place_test_order_ib.py` entry script

**Files:**
- Create: `place_test_order_ib.py`

**Interfaces:**
- Consumes: `backends.ib.order_client.IBOrderClient.place_order`/
  `get_order_status`/`cancel_order` (Task 1).
- Produces: `async def run() -> None` and `main() -> None`. No other code
  depends on this script.

- [ ] **Step 1: Write `place_test_order_ib.py`**

```python
# place_test_order_ib.py
import asyncio

from backends.ib.order_client import IBOrderClient

SYMBOL = "AAPL"
QUANTITY = 1
LIMIT_PRICE = 50.0  # well below any plausible AAPL price, won't fill immediately


async def run() -> None:
    client = IBOrderClient()

    placed = await client.place_order(
        symbol=SYMBOL, side="BUY", quantity=QUANTITY, order_type="LIMIT", limit_price=LIMIT_PRICE
    )
    print("placed:", placed)
    order_id = placed["order_id"]

    await asyncio.sleep(1)
    status = await client.get_order_status(order_id)
    print("status after place:", status)

    cancelled = await client.cancel_order(order_id)
    print("cancelled:", cancelled)

    await asyncio.sleep(1)
    status_after_cancel = await client.get_order_status(order_id)
    print("status after cancel:", status_after_cancel)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing suite + Task 1's new tests; this script
has no unit test of its own — it is exercised manually in Task 3, the same
way `live_trade_stream_ib.py` and `place_test_order.py` were)

- [ ] **Step 3: Commit**

```bash
git add place_test_order_ib.py
git commit -m "feat: add IB paper-trading order place/query/cancel entry script"
```

---

### Task 3: Manual end-to-end verification against the real IB paper account

**Files:** none (manual verification step, no code changes — except fixes to
the status-settling wait or field names in `backends/ib/order_client.py`,
described in Step 3, if the real `ib_async` behavior disagrees with the
documented assumption)

**Interfaces:**
- Consumes: `main()` from `place_test_order_ib.py` (Task 2), a running TWS or
  IB Gateway connected to a paper account, listening on `127.0.0.1:7497`
  (the same connection sub-project 3 uses).

- [ ] **Step 1: Confirm preconditions, then run the script**

Confirm TWS/IB Gateway is running and logged into a paper account with API
connections enabled on port 7497 (same precondition as sub-project 3 — order
placement does not require market-data entitlements, so this can run even if
sub-project 3's Task 4 is still blocked on that unrelated issue).

Run: `python3 place_test_order_ib.py`
Expected: prints the placement response (containing a non-zero `order_id`
and a status like `"PendingSubmit"` or `"Submitted"`), the status-after-place
response, the cancellation response (status moving toward `"Cancelled"` or
`"PendingCancel"`), and the status-after-cancel response, with no unhandled
exceptions.

- [ ] **Step 2: Sanity-check each printed step**

Confirm: the placement response's `order_id` is a positive integer; the
status-after-place lookup finds that same `order_id` (confirms
`get_order_status` works); the cancellation response succeeds; and the
status-after-cancel lookup shows a terminal cancelled state (`"Cancelled"` or
`"ApiCancelled"`, per `OrderStatus.DoneStates` in the Global Constraints
section above) rather than still `"PendingCancel"` — if it's still pending,
increase the `asyncio.sleep` duration in `place_test_order_ib.py` and re-run
before concluding something is wrong.

- [ ] **Step 3: Fix the status-settling wait or field names if the real feed disagrees**

If the script raises an unexpected error, or status never settles to a
terminal state even after increasing the sleep duration, capture the actual
behavior, adjust `backends/ib/order_client.py` accordingly (e.g. poll
`get_order_status` in a short retry loop instead of a single fixed sleep),
update `tests/test_ib_order_client.py` to match the corrected behavior,
re-run `pytest -v` to confirm everything still passes, and commit:

```bash
git add backends/ib/order_client.py tests/test_ib_order_client.py
git commit -m "fix: correct IB order status settling against live paper feed"
```

If the behavior already matches (no fix needed), skip the commit — this task
ends with just the manual confirmation in Step 2.

- [ ] **Step 4: Update the progress ledger**

Append to `.superpowers/sdd/progress.md`:
`SP5 Task 3: complete (manual verification, real IB paper account, <what you observed>)`

- [ ] **Step 5: Dispatch the final whole-branch review**

Per `superpowers:subagent-driven-development`'s process: use the commit
before Task 1 (the spec+plan commit, `73a0d6d`) as the base. Run
`scripts/review-package 73a0d6d HEAD` (from the `subagent-driven-development`
skill's directory) as the diff package, dispatch a code-reviewer subagent on
the most capable available model per that skill's `code-reviewer.md`
template, and resolve any Critical/Important findings before considering
sub-project 5 complete.

## Out of scope (reminder, per spec)

Do not add: order modification, multiple concurrent orders, multi-instrument
support, position/balance queries, or any Nautilus
`ExecutionEngine`/`TradingNode`/`Order` integration. These belong to later
sub-projects.
