# Design: KIS Order Execution Adapter (Sub-project 4 of 6)

## Context

Sub-projects 1-3 (KIS daily-bar ingestion, KIS real-time trade-tick streaming,
IB real-time trade-tick streaming) are complete or substantially complete. The
original plan's item 4 ("KIS + IB execution adapters") bundles two independent
venues with unrelated connection mechanics, the same problem sub-project 2 hit
with the original item "KIS+IB data adapters" — so it is re-split the same way:

1. ~~KIS data catalog ingestion~~ (done).
2. ~~KIS real-time trade tick streaming~~ (done).
3. IB real-time trade tick streaming (3/4 tasks done, blocked on IB market-data
   entitlements — unrelated to this spec).
4. **KIS order execution adapter** (this spec).
5. IB order execution adapter (future sub-project — separate, uses `ib_async`'s
   order API, different connection/account model).
6. Multi-venue strategy + backtest runner.

This sub-project builds a standalone KIS REST client that places, queries, and
cancels stock orders against KIS's **mock trading (모의투자)** environment, and
a console script that exercises the full place → query → cancel flow for a
single test order. It does **not** wire into Nautilus's `ExecutionEngine` /
`TradingNode` yet. Nautilus's `Order` types are managed by the execution engine
and aren't designed to be constructed standalone outside that context, so —
mirroring how sub-projects 1-3 deferred `DataEngine`/`TradingNode` integration
until the raw streaming/ingestion plumbing was proven — this sub-project
returns and prints raw KIS response data (dicts), not Nautilus domain objects.
That integration is deferred to sub-project 6.

## Decisions made during brainstorming

- **Scope**: KIS only. IB's order API (via `ib_async`) is a separate
  sub-project — different connection model and account/permission system, no
  shared code worth coupling them for.
- **Environment**: KIS mock trading (모의투자), not the real-money account.
  Mock trading uses a separate base URL
  (`https://openapivts.koreainvestment.com:29443` instead of
  `https://openapi.koreainvestment.com:9443`) and `V`-prefixed TR IDs instead
  of `T`-prefixed ones, but otherwise the same REST/OAuth shape already used
  by `KISClient`/`KISAuth` in sub-project 1.
- **Operations in scope**: place order (buy or sell, market or limit), query
  order status, cancel order. All three, not just place+query — cancel is
  needed to safely test against a real (mock) order book without leaving
  resting orders around.
- **Order types**: both market and limit. Limit orders are needed so a test
  order can sit unfilled long enough to query and cancel it; market orders are
  in scope too since they're the simpler/more common case and KIS's order API
  handles both through the same endpoint with a different `ORD_DVSN` code.
- **Single instrument, single size**: `005930`, quantity `1` (consistent with
  prior sub-projects' single-instrument scope).
- **Output**: console print, for verification only. No Nautilus
  `ExecutionEngine`/`TradingNode`/`Order` integration in this sub-project.
- **New account configuration**: KIS order endpoints require an account number
  split into `CANO` (8-digit account number) and `ACNT_PRDT_CD` (2-digit
  product code), neither of which the data-only endpoints from sub-project 1-2
  needed. These are added as new `.env` entries (`KIS_CANO`, `KIS_ACNT_PRDT_CD`)
  for the user's mock-trading account — gitignored like the existing KIS
  credentials, never printed or committed.

## Known risk: KIS order TR IDs and field names unverified

The mock-trading order TR IDs (`VTTC0802U` for buy, `VTTC0801U` for sell,
`VTTC0803U` for the combined modify/cancel endpoint, `VTTC8001R` for the
daily order/fill inquiry) and their request/response field names (`ORD_DVSN`,
`ODNO`, etc.) are implemented here from documented KIS API behavior, without
re-verifying them against a live mock-trading connection at design time. This
is the same category of risk sub-project 2 flagged for the KIS WebSocket wire
format. Unlike that case, KIS's REST order API responds synchronously with
`rt_cd`/`msg1` on every call — a wrong TR ID or missing required field fails
loudly with KIS's own error message on the very first real call, rather than
silently producing wrong data. The plan includes a manual end-to-end
verification task (mirroring sub-project 1's and 2's final manual tasks) where
the real API responses are confirmed; if a TR ID or field name is wrong, that
task fixes it using the error message KIS returns. The status-mapping field
names used by `_row_to_status_dict` (`TOT_CCLD_QTY`, `NCCS_QTY`, `CNCL_YN`)
are likewise documented-but-unverified against a live connection, and fall
into this same risk category. **Confirmed live (2026-06-23):** KIS's
trading-domain endpoints (order-cash, inquire-daily-ccld, order-rvsecncl)
return UPPERCASE response field names (e.g. a real order-cash response
included `{"output": {"ODNO": ..., "ORD_TMD": ...}}`), unlike the
quotations-domain endpoints (sub-project 1's `get_daily_price`, which returns
lowercase fields like `stck_bsop_date`). `ODNO` is confirmed; `TOT_CCLD_QTY`/
`NCCS_QTY`/`CNCL_YN` follow the same convention but are not yet confirmed for
the inquire-daily-ccld endpoint specifically.

**Additional account-setup finding (2026-06-23):** KIS requires a mock-trading
app key/secret and account number (`KIS_CANO`'s sibling values
`KIS_MOCK_APP_KEY`/`KIS_MOCK_APP_SECRET`/`KIS_MOCK_CANO` in `.env`) that are
**separate** from the real-trading credentials used by `KISClient` — the
real-trading app key is rejected by mock order endpoints (KIS error
`EGW02007`: "해당 앱키는 모의투자용 앱키가 아닙니다"), and the real account
number is rejected too (`IGW00002`: account number mismatch). `place_test_order.py`
uses `KIS_MOCK_APP_KEY`/`KIS_MOCK_APP_SECRET`/`KIS_MOCK_CANO` for the
`KISOrderClient`, while `KISClient` (for the reference price lookup) keeps
using the real-trading `KIS_APP_KEY`/`KIS_APP_SECRET`. Also: KIS rejects limit
prices that aren't a multiple of KRX's tick size (호가단위, which varies by
price range) with `"모의투자 주문처리가 안되었습니다(호가단위 오류)"` —
`place_test_order.py` rounds its computed limit price down to a valid tick.

**Known limitation, accepted (2026-06-23):** `get_order_status` (and by
extension a `cancel_order` design that depended on it) does not work against
this mock-trading account — `inquire-daily-ccld` returns an empty `output1`
for the placed order regardless of `CCLD_DVSN`/`PDNO` parameter combination
tried (`"00"`/`"01"`/`"02"`, with and without `PDNO` filled in), even though
the order genuinely exists (`output2.tot_ord_qty` reflects it) and cancels
successfully via `order-rvsecncl`. This looks like a mock-trading-environment
limitation specific to querying unfilled orders, not a request-shape bug —
but it's unverified whether the real-trading domain has the same limitation.
Decision: `cancel_order` does not depend on `get_order_status`'s result (see
Architecture section below); `get_order_status` itself is left as originally
designed and is expected to keep returning `None` in this mock environment.
This is acceptable because this sub-project's adapters aren't wired into any
actual trading flow yet (no Nautilus `ExecutionEngine` integration, and
Nautilus backtesting doesn't call these adapters at all) — revisit
`get_order_status` only when real execution (live or mock) is actually wired
up later, at which point re-verify against whichever account is in use.

## Architecture

```
nautilus-multi-venue/
  backends/kis/
    order_client.py   # KISOrderClient.place_order/get_order_status/cancel_order
  place_test_order.py # entry point: place -> query -> cancel -> query, prints each step
  tests/
    test_order_client.py
```

### `backends/kis/order_client.py`

- `KISOrderClient(app_key: str, app_secret: str, cano: str, acnt_prdt_cd: str,
  auth: KISAuth | None = None, base_url: str =
  "https://openapivts.koreainvestment.com:29443", session: requests.Session |
  None = None)`: mirrors `KISClient`'s constructor shape (reuses `KISAuth` for
  token caching/401-retry), but defaults `base_url` to the mock-trading domain
  since that's this sub-project's only target.
- `place_order(code: str, side: str, quantity: int, order_division: str,
  price: int | None = None) -> dict`: `side` is `"BUY"` or `"SELL"`,
  `order_division` is `"LIMIT"` or `"MARKET"` (mapped internally to KIS's
  `ORD_DVSN` codes `"00"`/`"01"`). Posts to
  `/uapi/domestic-stock/v1/trading/order-cash` with TR ID `VTTC0802U` (buy) or
  `VTTC0801U` (sell). `price` is required for `"LIMIT"`, ignored (sent as
  `"0"`) for `"MARKET"`. Returns a normalized
  `{"order_id": str, "status": str, "filled": float, "remaining": float}`
  dict (matching `IBOrderClient`'s shape, except `order_id` is `str` for KIS
  rather than `int`) — since KIS's placement response only confirms
  acceptance, `status` is always `"SUBMITTED"`, `filled` is always `0.0`, and
  `remaining` is the requested `quantity`. Raises `RuntimeError` if `rt_cd !=
  "0"`, and raises `KeyError` naturally if the expected `output.ODNO` field is
  missing (no silent fallback — a missing order number means something is
  wrong and the caller needs to know).
- `get_order_status(order_date: str, order_no: str) -> dict | None`: GETs
  `/uapi/domestic-stock/v1/trading/inquire-daily-ccld` with TR ID `VTTC8001R`,
  filters the returned order list (`output1`) for the row matching `order_no`,
  and maps that row through `_row_to_status_dict` into the same normalized
  `{"order_id", "status", "filled", "remaining"}` shape (deriving `status` as
  `"CANCELLED"`/`"FILLED"`/`"PARTIAL"`/`"OPEN"` from `TOT_CCLD_QTY`,
  `NCCS_QTY`, and `CNCL_YN`), or returns `None` if not found (e.g., already
  filtered out of the day's list — this is a legitimate "not found" case,
  unlike the order-placement response, so it returns `None` rather than
  raising).
- `cancel_order(order_no: str, code: str, quantity: int) -> dict`: posts to
  `/uapi/domestic-stock/v1/trading/order-rvsecncl` with TR ID `VTTC0803U` and
  `RVSE_CNCL_DVSN_CD = "02"` (cancel, as opposed to `"01"` modify), then
  returns `{"order_id": order_no, "status": "CANCELLED", "filled": 0.0,
  "remaining": 0.0}` directly — it does **not** delegate to
  `get_order_status` (an earlier version of this design did; see the "Known
  limitation, accepted" note above for why that was reverted after live
  testing). Same
  error handling as `place_order` for the cancel call itself.
- Same 401-retry-after-refresh pattern as `KISClient._fetch_page`, factored
  into a small shared retry helper used by all three methods (the existing
  `KISClient` doesn't share this helper since it only has one HTTP-calling
  method; with three methods here, extracting it avoids tripling the
  duplicated retry logic).

### `place_test_order.py`

1. Load env vars (`KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_CANO`,
   `KIS_ACNT_PRDT_CD`), construct `KISOrderClient`.
2. Place a `LIMIT` `BUY` order for `005930`, quantity `1`, at a price clearly
   below the current market price (so it doesn't fill immediately) — read the
   current price first via sub-project 1's `KISClient.get_daily_price` (most
   recent close) and set the limit price to e.g. 90% of that, to keep this
   script self-contained without requiring a separate manual price lookup.
3. Print the placement response (order number, etc.).
4. Call `get_order_status` for that order number and print the result.
5. Call `cancel_order` for that order number and print the result.
6. Call `get_order_status` again and print the result, to visually confirm the
   cancellation took effect (exact confirmation signal — e.g. a status field
   showing "취소" — is determined during the manual verification task, since
   it depends on the real response shape).

## Error handling

- Auth/account-number failures → raise immediately, no retry (consistent with
  sub-projects 1-2).
- `rt_cd != "0"` on any of the three calls → `RuntimeError` with KIS's own
  `msg1` included, so a wrong TR ID or rejected order is never silently
  swallowed.
- Missing `output.ODNO` after a successful (`rt_cd == "0"`) placement →
  `KeyError` propagates naturally; this is a "fail loud" case per the Known
  Risk section, not something to catch and re-raise with a nicer message.

## Testing

- `test_order_client.py`: mocked HTTP responses for `place_order`,
  `get_order_status`, and `cancel_order`, following `test_client.py`'s pattern
  from sub-project 1 (mocked `requests.Session`, asserting on TR ID/params
  sent and on parsing of the mocked response body, including a 401-retry test
  and an `rt_cd != "0"` error test for at least `place_order`).
- Manual end-to-end task (mirroring sub-project 1's and 2's final manual
  tasks): run `place_test_order.py` against the real KIS mock-trading account
  during KRX market hours, confirm the full place → query → cancel → query
  flow behaves as expected, and fix the TR IDs/field names in
  `order_client.py` if the real API disagrees with the documented assumption.

## Out of scope (deferred to later sub-projects)

- IB order execution adapter.
- Order modification (정정) — only cancel is in scope; modify uses the same
  endpoint with `RVSE_CNCL_DVSN_CD = "01"` but isn't needed yet.
- Multiple concurrent orders, multi-instrument support, position/balance
  queries.
- Nautilus `ExecutionEngine`/`TradingNode`/`Order` integration.
