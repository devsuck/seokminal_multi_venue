# Design: KIS Real-Time Trade Tick Streaming (Sub-project 2 of 5)

## Context

Sub-project 1 (KIS daily-bar batch ingestion into a `ParquetDataCatalog`) is complete
and merged to `main`. The original four-part scope has been re-split into five, since
sub-project 2 ("KIS+IB data adapters") bundled two independent venues with unrelated
connection mechanics:

1. ~~Data catalog ingestion~~ (done).
2. **KIS real-time trade tick streaming** (this spec).
3. IB live data adapter (future sub-project — separate, uses `ib_insync`/TWS).
4. KIS + IB execution adapters.
5. Multi-venue strategy + backtest runner.

This sub-project builds a standalone KIS WebSocket client that streams real-time
trade ticks (실시간체결) for a single instrument and prints mapped `TradeTick` objects
to the console. It does **not** wire into Nautilus's `LiveDataEngine` / `TradingNode`
yet — that integration is deferred to a later sub-project once the raw streaming
plumbing is proven to work against the real KIS WebSocket feed.

## Decisions made during brainstorming

- **Scope**: KIS only. IB's real-time feed (via `ib_insync`) is a separate
  sub-project — different connection model (TWS/Gateway socket vs. KIS's WebSocket +
  REST approval-key flow), no shared code worth coupling them for.
- **Data type**: real-time trade ticks only (실시간체결, KIS TR ID `H0STCNT0`). Order
  book / quote depth (실시간호가) is excluded — it requires a different TR ID, a more
  complex multi-level field layout, and isn't needed yet.
- **Output**: console print, for verification only. No Nautilus `DataEngine`/`TradingNode`
  integration in this sub-project — that's deferred until the parsing/connection layer
  is proven against the live feed.
- **Single instrument**: `005930` (consistent with sub-project 1).

## Known risk: KIS wire format accuracy

The KIS real-time WebSocket protocol (approval-key exchange, JSON subscribe envelope,
pipe-delimited (`|`) message framing with `^`-delimited fields inside the data segment)
is implemented here from documented behavior, without an internet connection to
re-verify the exact field order against KIS's current published spec at
implementation time. The implementation must treat field-index-to-meaning mapping
(especially the 체결구분 aggressor-side code) as **unverified until tested against a
real connection**. The plan includes a manual end-to-end verification task (mirroring
sub-project 1's Task 6) where the real field layout is confirmed against live data
before this sub-project is considered done. If indices are wrong, that task fixes the
parsing constants — it is expected to require iteration, not a sign the design is wrong.

## Architecture

```
nautilus-multi-venue/
  backends/kis/
    ws_auth.py     # get_approval_key() -> str (POST /oauth2/Approval)
    ws_client.py    # KISWebSocketClient.stream_trades(code) -> AsyncIterator[str]
  adapters/
    data_provider.py  # + parse_kis_trade_message(raw) -> dict | None
                       # + map_kis_trade_tick(fields, instrument_id) -> TradeTick
  live_trade_stream.py # entry point: connect, subscribe, parse+map+print each tick
  tests/
    test_ws_auth.py
    test_ws_client.py
    test_data_provider.py  # (extended with trade-tick parsing/mapping tests)
```

### `backends/kis/ws_auth.py`

- `get_approval_key(app_key: str, app_secret: str, base_url: str =
  "https://openapi.koreainvestment.com:9443", session: requests.Session | None =
  None) -> str`: POSTs `{"grant_type": "client_credentials", "appkey": app_key,
  "secretkey": app_secret}` to `/oauth2/Approval`, returns the `approval_key` field
  from the JSON response. No caching — called once per process/connection, unlike the
  REST OAuth token in sub-project 1.

### `backends/kis/ws_client.py`

- `KISWebSocketClient`: holds the approval key and a WebSocket URL
  (`ws://ops.koreainvestment.com:21000` for the real account domain — KIS's real-time
  feed is unencrypted `ws://`, not `wss://`).
- `async def stream_trades(self, code: str) -> AsyncIterator[str]`: opens the
  connection (via the `websockets` library, already installed), sends the JSON
  subscribe envelope (`header.approval_key`, `header.tr_type="1"`,
  `body.input.tr_id="H0STCNT0"`, `body.input.tr_key=code`), then yields each raw
  text frame received as-is. Does not parse — parsing is the data_provider's job, so
  this class can be tested by injecting a fake message source instead of a real
  socket.
- No reconnect/backoff logic in this sub-project — a dropped connection just ends
  the generator. Reconnection is deferred to whichever sub-project wires this into a
  long-running live trading process.

### `adapters/data_provider.py` (additions)

- `parse_kis_trade_message(raw: str) -> dict | None`: KIS frames look like
  `"0|H0STCNT0|001|<data>"` where `<data>` is `^`-joined fields. Non-data frames
  (JSON acks, PINGPONG) don't start with a digit+`|` pattern and return `None`.
  For a data frame, splits on `|`, takes the last segment, splits on `^`, and returns
  a dict with the fields known to be needed for trade-tick mapping: `code` (index 0),
  `time` (index 1, `HHMMSS`), `price` (index 2), `volume` (index 12, per KIS's
  documented field order for `H0STCNT0` — **flagged as the risk above**), and
  `side_code` (index 21, raw string — meaning to be confirmed against real data).
- `map_kis_trade_tick(fields: dict, instrument_id: InstrumentId, price_precision:
  int) -> TradeTick`: builds a Nautilus `TradeTick` using `Price`/`Quantity` at the
  instrument's precision, `AggressorSide.BUYER`/`SELLER`/`NO_AGGRESSOR` based on
  `side_code` (defensive: unrecognized codes map to `NO_AGGRESSOR` rather than
  raising), a `TradeId` built from `code + time + a per-message sequence counter`
  (KIS doesn't supply a trade ID directly), and `ts_event`/`ts_init` derived from
  `time` combined with today's date in KST, converted to UTC nanoseconds.

### `live_trade_stream.py`

1. Load env vars, build `Equity` instrument (reuse `build_xkrx_equity` from
   sub-project 1).
2. Call `get_approval_key(...)`.
3. Construct `KISWebSocketClient`, call `stream_trades("005930")`.
4. For each raw message: `parse_kis_trade_message` → if not `None`,
   `map_kis_trade_tick` → print the resulting `TradeTick`.
5. Runs until interrupted (Ctrl+C) or the connection drops.

## Error handling

- Approval-key fetch failure → raise immediately with the HTTP error, no retry (this
  is a startup-time call, not a long-running loop).
- Non-data frames (acks, pings) → `parse_kis_trade_message` returns `None`, silently
  skipped by the entry script.
- Malformed/unexpected data frames (wrong field count) → `parse_kis_trade_message`
  raises `ValueError` with the raw frame included, so the entry script crashes loudly
  rather than silently mismapping fields — important given the wire-format risk noted
  above.

## Testing

- `test_ws_auth.py`: mocked HTTP response, same pattern as sub-project 1's
  `test_auth.py`.
- `test_ws_client.py`: tests `stream_trades` against a fake WebSocket connection
  object (injected, matching the `websockets` client API surface used) that yields a
  canned sequence of messages, confirming the subscribe envelope sent and the
  messages yielded.
- `test_data_provider.py` additions: `parse_kis_trade_message` and
  `map_kis_trade_tick` tested against hand-constructed sample frames matching the
  documented `H0STCNT0` field layout — fixtures double as the executable
  documentation of the assumed wire format, so the manual verification task has a
  precise list of fields to confirm or correct.
- Manual end-to-end task (mirroring sub-project 1's Task 6): run
  `live_trade_stream.py` against the real KIS WebSocket during market hours, confirm
  printed ticks have sane price/volume/side values, and fix the field indices in
  `parse_kis_trade_message` if the real wire format disagrees with the documented
  assumption.

## Out of scope (deferred to later sub-projects)

- IB real-time data adapter.
- Order book / quote depth (실시간호가) streaming.
- Reconnect/backoff, multi-instrument subscription, and Nautilus
  `DataEngine`/`TradingNode` integration.
