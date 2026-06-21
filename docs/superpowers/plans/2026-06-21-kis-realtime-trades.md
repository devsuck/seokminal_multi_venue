# KIS Real-Time Trade Tick Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect to KIS's real-time WebSocket feed, subscribe to trade ticks
(실시간체결, TR ID `H0STCNT0`) for `005930`, parse and map each tick into a Nautilus
`TradeTick`, and print it to the console — proving the connection/parsing layer works
before any later sub-project wires it into Nautilus's live `DataEngine`.

**Architecture:** A WebSocket approval-key fetcher (`backends/kis/ws_auth.py`,
sync `requests`, same pattern as sub-project 1's REST OAuth client) gets the
credential needed to open the socket. A streaming client (`backends/kis/ws_client.py`,
async, using the already-installed `websockets` library) opens the connection,
sends the subscribe envelope, and yields raw frames — with the actual socket
connection injectable so it's testable without a network. A pure parsing/mapping
layer (`adapters/data_provider.py` additions) converts raw frames into Nautilus
`TradeTick` objects, kept separate from the I/O so it's unit-testable with fixed
fixture strings. An entry script (`live_trade_stream.py`) wires these together.

**Tech Stack:** Python 3.11+, `nautilus_trader` (v1.228.0), `requests`, `websockets`
(v15.0.1, already installed), `pytest`, `pytest-asyncio` (new dependency for this
plan — added in Task 3).

## Global Constraints

- KIS only — IB's real-time feed is a separate, later sub-project.
- Trade ticks only (실시간체결, `H0STCNT0`). No order book / quote depth streaming.
- Console-print output only. No Nautilus `DataEngine`/`TradingNode` integration yet.
- Single instrument: `005930`.
- The exact byte-level field layout of KIS's `H0STCNT0` message (specifically: which
  index holds 체결구분/aggressor-side, and the exact field count per record) is
  **unverified against a live connection** — implemented from documented structure.
  Task 5 (manual verification) is expected to require fixing field indices if the
  real feed disagrees; that is not a sign Tasks 1-4 were done wrong.
- No real credentials in code or tests — the live script reads `KIS_APP_KEY`/
  `KIS_APP_SECRET` from environment via `.env` (already set up in sub-project 1).

---

### Task 1: KIS WebSocket approval-key client

**Files:**
- Create: `backends/kis/ws_auth.py`
- Test: `tests/test_ws_auth.py`

**Interfaces:**
- Consumes: `requests` library; env vars `KIS_APP_KEY`, `KIS_APP_SECRET` (read by
  the caller in Task 4, not by this module itself).
- Produces: `get_approval_key(app_key: str, app_secret: str, base_url: str =
  "https://openapi.koreainvestment.com:9443", session: requests.Session | None =
  None) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ws_auth.py
from unittest.mock import MagicMock

from backends.kis.ws_auth import get_approval_key


def test_get_approval_key_posts_credentials_and_returns_key():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"approval_key": "approval-abc123"}
    response.raise_for_status.return_value = None
    session.post.return_value = response

    key = get_approval_key(app_key="key", app_secret="secret", session=session)

    assert key == "approval-abc123"
    session.post.assert_called_once()
    call_kwargs = session.post.call_args.kwargs
    assert call_kwargs["json"]["grant_type"] == "client_credentials"
    assert call_kwargs["json"]["appkey"] == "key"
    assert call_kwargs["json"]["secretkey"] == "secret"
    url = session.post.call_args.args[0]
    assert url.endswith("/oauth2/Approval")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ws_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backends.kis.ws_auth'`

- [ ] **Step 3: Implement `backends/kis/ws_auth.py`**

```python
# backends/kis/ws_auth.py
import requests


def get_approval_key(
    app_key: str,
    app_secret: str,
    base_url: str = "https://openapi.koreainvestment.com:9443",
    session: requests.Session | None = None,
) -> str:
    active_session = session or requests.Session()
    response = active_session.post(
        f"{base_url}/oauth2/Approval",
        json={
            "grant_type": "client_credentials",
            "appkey": app_key,
            "secretkey": app_secret,
        },
    )
    response.raise_for_status()
    return response.json()["approval_key"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ws_auth.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backends/kis/ws_auth.py tests/test_ws_auth.py
git commit -m "feat: add KIS WebSocket approval-key client"
```

---

### Task 2: Parse and map KIS trade-tick frames

**Files:**
- Modify: `adapters/data_provider.py` (add new functions; existing
  `build_xkrx_equity`, `bar_type_for`, `map_kis_daily_bar` are untouched)
- Test: `tests/test_data_provider.py` (add new test functions; existing tests
  untouched)

**Interfaces:**
- Consumes: raw KIS WebSocket text frames (strings) and an `InstrumentId` (e.g.
  from `build_xkrx_equity("005930").id`, reused from sub-project 1).
- Produces:
  - `parse_kis_trade_message(raw: str) -> dict | None` returning `None` for
    non-trade frames (e.g. JSON acks), or a dict with keys `code`, `time`
    (`"HHMMSS"` string), `price` (numeric string), `volume` (numeric string),
    `side_code` (raw single-character string) for trade frames. Raises
    `ValueError` if a frame claims to be a trade frame but has the wrong field
    count.
  - `map_kis_trade_tick(fields: dict, instrument_id: InstrumentId,
    price_precision: int, trade_date: datetime.date, sequence: int) ->
    TradeTick`.

KIS's real-time frame format: `"<encrypt_flag>|<tr_id>|<data_count>|<data>"`
where `<data>` is `^`-joined fields, one fixed-width record per trade
(documented field count for `H0STCNT0` is 46 fields; this plan uses indices `0`
code, `1` time, `2` price, `12` volume, `21` side_code — flagged in Global
Constraints as unverified against the live feed).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_data_provider.py — add these, do not remove existing tests
import datetime as dt

from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId

from adapters.data_provider import map_kis_trade_tick, parse_kis_trade_message


def _trade_record(code="005930", time="093354", price="70000", volume="15", side_code="1") -> str:
    fields = ["0"] * 46
    fields[0] = code
    fields[1] = time
    fields[2] = price
    fields[12] = volume
    fields[21] = side_code
    return "^".join(fields)


def test_parse_kis_trade_message_extracts_known_fields():
    raw = f"0|H0STCNT0|001|{_trade_record()}"

    result = parse_kis_trade_message(raw)

    assert result == {
        "code": "005930",
        "time": "093354",
        "price": "70000",
        "volume": "15",
        "side_code": "1",
    }


def test_parse_kis_trade_message_returns_none_for_non_trade_frame():
    raw = '{"header":{"tr_id":"PINGPONG"}}'

    assert parse_kis_trade_message(raw) is None


def test_parse_kis_trade_message_raises_on_wrong_field_count():
    raw = "0|H0STCNT0|001|" + "^".join(["0"] * 10)

    try:
        parse_kis_trade_message(raw)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert raw in str(exc)


def test_map_kis_trade_tick_converts_fields_to_trade_tick():
    instrument_id = InstrumentId.from_str("005930.XKRX")
    fields = {
        "code": "005930",
        "time": "093354",
        "price": "70000",
        "volume": "15",
        "side_code": "1",
    }

    tick = map_kis_trade_tick(
        fields,
        instrument_id,
        price_precision=0,
        trade_date=dt.date(2024, 6, 3),
        sequence=7,
    )

    assert tick.instrument_id == instrument_id
    assert tick.price.as_double() == 70000.0
    assert tick.size.as_double() == 15.0
    assert tick.aggressor_side == AggressorSide.BUYER
    assert str(tick.trade_id) == "005930-093354-7"
    assert tick.ts_event == 1717374834000000000  # 2024-06-03 09:33:54 KST -> UTC ns


def test_map_kis_trade_tick_maps_sell_side_code():
    instrument_id = InstrumentId.from_str("005930.XKRX")
    fields = {"code": "005930", "time": "093354", "price": "70000", "volume": "15", "side_code": "5"}

    tick = map_kis_trade_tick(fields, instrument_id, price_precision=0, trade_date=dt.date(2024, 6, 3), sequence=1)

    assert tick.aggressor_side == AggressorSide.SELLER


def test_map_kis_trade_tick_maps_unknown_side_code_to_no_aggressor():
    instrument_id = InstrumentId.from_str("005930.XKRX")
    fields = {"code": "005930", "time": "093354", "price": "70000", "volume": "15", "side_code": "9"}

    tick = map_kis_trade_tick(fields, instrument_id, price_precision=0, trade_date=dt.date(2024, 6, 3), sequence=1)

    assert tick.aggressor_side == AggressorSide.NO_AGGRESSOR
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_data_provider.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_kis_trade_message' from 'adapters.data_provider'`

- [ ] **Step 3: Add to `adapters/data_provider.py`**

Add these imports at the top (alongside the existing ones — do not remove
`build_xkrx_equity`, `bar_type_for`, `map_kis_daily_bar` or their imports):

```python
from zoneinfo import ZoneInfo

from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import TradeId
```

Add these constants and functions at the end of the file:

```python
TRADE_TR_ID = "H0STCNT0"
TRADE_FIELD_COUNT = 46
TRADE_CODE_IDX = 0
TRADE_TIME_IDX = 1
TRADE_PRICE_IDX = 2
TRADE_VOLUME_IDX = 12
TRADE_SIDE_IDX = 21

SIDE_CODE_BUY = "1"
SIDE_CODE_SELL = "5"

KST = ZoneInfo("Asia/Seoul")


def parse_kis_trade_message(raw: str) -> dict | None:
    parts = raw.split("|")
    if len(parts) < 4 or parts[1] != TRADE_TR_ID:
        return None

    data = parts[3]
    record = data.split("^")
    if len(record) != TRADE_FIELD_COUNT:
        raise ValueError(
            f"expected {TRADE_FIELD_COUNT} fields in KIS trade frame, got {len(record)}: {raw!r}"
        )

    return {
        "code": record[TRADE_CODE_IDX],
        "time": record[TRADE_TIME_IDX],
        "price": record[TRADE_PRICE_IDX],
        "volume": record[TRADE_VOLUME_IDX],
        "side_code": record[TRADE_SIDE_IDX],
    }


def map_kis_trade_tick(
    fields: dict,
    instrument_id: InstrumentId,
    price_precision: int,
    trade_date: dt.date,
    sequence: int,
) -> TradeTick:
    side_code = fields["side_code"]
    if side_code == SIDE_CODE_BUY:
        aggressor_side = AggressorSide.BUYER
    elif side_code == SIDE_CODE_SELL:
        aggressor_side = AggressorSide.SELLER
    else:
        aggressor_side = AggressorSide.NO_AGGRESSOR

    time_str = fields["time"]
    event_dt = dt.datetime.combine(
        trade_date,
        dt.time(int(time_str[0:2]), int(time_str[2:4]), int(time_str[4:6])),
        tzinfo=KST,
    )
    ts_event = dt_to_unix_nanos(event_dt)

    return TradeTick(
        instrument_id=instrument_id,
        price=Price(float(fields["price"]), price_precision),
        size=Quantity(float(fields["volume"]), 0),
        aggressor_side=aggressor_side,
        trade_id=TradeId(f"{fields['code']}-{fields['time']}-{sequence}"),
        ts_event=ts_event,
        ts_init=ts_event,
    )
```

`adapters/data_provider.py` already has `import datetime as dt` at the top of
the file (from sub-project 1's Task 4) — reuse it, do not add a second import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_provider.py -v`
Expected: 9 passed (3 existing from sub-project 1 + 6 new)

- [ ] **Step 5: Commit**

```bash
git add adapters/data_provider.py tests/test_data_provider.py
git commit -m "feat: parse and map KIS real-time trade-tick frames"
```

---

### Task 3: KIS WebSocket streaming client

**Files:**
- Create: `backends/kis/ws_client.py`
- Test: `tests/test_ws_client.py`
- Modify: `pyproject.toml` (add `pytest-asyncio` dev dependency and asyncio test
  config)

**Interfaces:**
- Consumes: an approval key string (from `get_approval_key`, Task 1); the
  `websockets` library (already installed, v15.0.1).
- Produces: `class KISWebSocketClient` with constructor
  `KISWebSocketClient(approval_key: str, base_url: str =
  "ws://ops.koreainvestment.com:21000", connect_fn: Callable[[str], Any] =
  websockets.connect)` and async generator method `async def
  stream_trades(self, code: str) -> AsyncIterator[str]` that connects, sends the
  subscribe envelope, and yields each raw text frame received.

- [ ] **Step 1: Add `pytest-asyncio` to the project**

Edit `pyproject.toml`'s `[project.optional-dependencies]` section:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]
```

Add this section (new, after `[tool.pytest.ini_options]`):

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

(If `[tool.pytest.ini_options]` already has `testpaths = ["tests"]` from
sub-project 1, just add the `asyncio_mode = "auto"` line inside that existing
section — don't duplicate the section header.)

Run: `pip install -e ".[dev]"`
Expected: installs `pytest-asyncio` successfully.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_ws_client.py
import json

from backends.kis.ws_client import KISWebSocketClient


class FakeConnection:
    def __init__(self, messages: list[str]) -> None:
        self.sent: list[str] = []
        self._messages = messages

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self):
        return self._iter_messages()

    async def _iter_messages(self):
        for message in self._messages:
            yield message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class FakeConnect:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self.called_with: str | None = None

    def __call__(self, uri: str):
        self.called_with = uri
        return self._connection


async def test_stream_trades_sends_subscribe_and_yields_messages():
    connection = FakeConnection(["msg1", "msg2"])
    connect_fn = FakeConnect(connection)
    client = KISWebSocketClient(approval_key="approval123", connect_fn=connect_fn)

    received = []
    async for message in client.stream_trades("005930"):
        received.append(message)

    assert received == ["msg1", "msg2"]
    assert connect_fn.called_with == "ws://ops.koreainvestment.com:21000"

    sent_envelope = json.loads(connection.sent[0])
    assert sent_envelope["header"]["approval_key"] == "approval123"
    assert sent_envelope["header"]["tr_type"] == "1"
    assert sent_envelope["body"]["input"]["tr_id"] == "H0STCNT0"
    assert sent_envelope["body"]["input"]["tr_key"] == "005930"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_ws_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backends.kis.ws_client'`

- [ ] **Step 4: Implement `backends/kis/ws_client.py`**

```python
# backends/kis/ws_client.py
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

TRADE_TR_ID = "H0STCNT0"


class KISWebSocketClient:
    def __init__(
        self,
        approval_key: str,
        base_url: str = "ws://ops.koreainvestment.com:21000",
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._approval_key = approval_key
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream_trades(self, code: str) -> AsyncIterator[str]:
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps(self._subscribe_message(code)))
            async for message in connection:
                yield message

    def _subscribe_message(self, code: str) -> dict:
        return {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": TRADE_TR_ID,
                    "tr_key": code,
                }
            },
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_ws_client.py -v`
Expected: 1 passed

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `pytest -v`
Expected: all tests pass (sub-project 1's 13 + this plan's tests so far)

- [ ] **Step 7: Commit**

```bash
git add backends/kis/ws_client.py tests/test_ws_client.py pyproject.toml
git commit -m "feat: add KIS WebSocket trade-tick streaming client"
```

---

### Task 4: Live trade-stream entry script

**Files:**
- Create: `live_trade_stream.py`
- Test: `tests/test_live_trade_stream.py`

**Interfaces:**
- Consumes: `backends.kis.ws_auth.get_approval_key` (Task 1),
  `backends.kis.ws_client.KISWebSocketClient.stream_trades` (Task 3),
  `adapters.data_provider.build_xkrx_equity`, `parse_kis_trade_message`,
  `map_kis_trade_tick` (Task 2 + sub-project 1).
- Produces: `async def run_stream(code: str, client: KISWebSocketClient,
  instrument_id: InstrumentId, price_precision: int, trade_date: datetime.date,
  print_fn=print) -> None` — consumes the stream, parses/maps each frame, calls
  `print_fn(tick)` for each successfully mapped tick, and silently skips frames
  where `parse_kis_trade_message` returns `None`. A `main()` synchronous entry
  point that loads `.env`, fetches the approval key, builds the client and
  instrument, and runs `asyncio.run(run_stream(...))` with `trade_date =
  datetime.date.today()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_live_trade_stream.py
import datetime as dt

from nautilus_trader.model.identifiers import InstrumentId

from live_trade_stream import run_stream


class FakeStreamingClient:
    def __init__(self, messages: list[str]) -> None:
        self._messages = messages

    async def stream_trades(self, code: str):
        for message in self._messages:
            yield message


def _trade_record(code="005930", time="093354", price="70000", volume="15", side_code="1") -> str:
    fields = ["0"] * 46
    fields[0] = code
    fields[1] = time
    fields[2] = price
    fields[12] = volume
    fields[21] = side_code
    return "^".join(fields)


async def test_run_stream_prints_mapped_ticks_and_skips_non_trade_frames():
    messages = [
        f"0|H0STCNT0|001|{_trade_record(price='70000')}",
        '{"header":{"tr_id":"PINGPONG"}}',
        f"0|H0STCNT0|001|{_trade_record(price='70100')}",
    ]
    client = FakeStreamingClient(messages)
    instrument_id = InstrumentId.from_str("005930.XKRX")
    printed = []

    await run_stream(
        code="005930",
        client=client,
        instrument_id=instrument_id,
        price_precision=0,
        trade_date=dt.date(2024, 6, 3),
        print_fn=printed.append,
    )

    assert len(printed) == 2
    assert printed[0].price.as_double() == 70000.0
    assert printed[1].price.as_double() == 70100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_live_trade_stream.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'live_trade_stream'`

- [ ] **Step 3: Implement `live_trade_stream.py`**

```python
# live_trade_stream.py
import asyncio
import datetime as dt
import os

from dotenv import load_dotenv
from nautilus_trader.model.identifiers import InstrumentId

from adapters.data_provider import (
    build_xkrx_equity,
    map_kis_trade_tick,
    parse_kis_trade_message,
)
from backends.kis.ws_auth import get_approval_key
from backends.kis.ws_client import KISWebSocketClient


async def run_stream(
    code: str,
    client: KISWebSocketClient,
    instrument_id: InstrumentId,
    price_precision: int,
    trade_date: dt.date,
    print_fn=print,
) -> None:
    sequence = 0
    async for raw_message in client.stream_trades(code):
        fields = parse_kis_trade_message(raw_message)
        if fields is None:
            continue

        sequence += 1
        tick = map_kis_trade_tick(fields, instrument_id, price_precision, trade_date, sequence)
        print_fn(tick)


def main() -> None:
    load_dotenv()

    code = "005930"
    app_key = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]

    approval_key = get_approval_key(app_key=app_key, app_secret=app_secret)
    client = KISWebSocketClient(approval_key=approval_key)
    instrument = build_xkrx_equity(code)

    asyncio.run(
        run_stream(
            code=code,
            client=client,
            instrument_id=instrument.id,
            price_precision=instrument.price_precision,
            trade_date=dt.date.today(),
        )
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_live_trade_stream.py -v`
Expected: 1 passed

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: all tests pass (sub-project 1's 13 + all of this plan's tests).

- [ ] **Step 6: Commit**

```bash
git add live_trade_stream.py tests/test_live_trade_stream.py
git commit -m "feat: add live KIS trade-tick stream entry script"
```

---

### Task 5: Manual end-to-end verification against the real KIS feed

**Files:** none (manual verification step, no code changes — except the
field-index fix described in Step 3, if needed)

**Interfaces:**
- Consumes: `main()` from `live_trade_stream.py` (Task 4), real `.env` (already
  present from sub-project 1, gitignored, not tracked).

- [ ] **Step 1: Run the script during KRX market hours (weekday, 09:00-15:30 KST)**

Run: `python3 live_trade_stream.py`
Expected: connects, subscribes, and prints a stream of `TradeTick` objects as
`005930` trades occur. If the market is closed, this will hang with no output —
that's expected (no trades to receive), not a bug; re-run during market hours.

- [ ] **Step 2: Sanity-check the printed ticks**

Confirm: `price` values are in a plausible range for Samsung Electronics (tens of
thousands of KRW), `size` values are plausible share counts, and
`aggressor_side` is either `BUYER` or `SELLER` for actual trades (not uniformly
`NO_AGGRESSOR`, which would indicate the side-code index is wrong).

- [ ] **Step 3: Fix field indices if the real feed disagrees**

If `price`/`volume`/`aggressor_side` look wrong, capture a few raw frames (add a
temporary `print(raw_message)` in `run_stream` before parsing, run again, then
remove it) and adjust `TRADE_PRICE_IDX`, `TRADE_VOLUME_IDX`, `TRADE_SIDE_IDX`, or
`SIDE_CODE_BUY`/`SIDE_CODE_SELL` in `adapters/data_provider.py` (Task 2) to match
the actual layout observed. Update the corresponding tests in
`tests/test_data_provider.py` to match the corrected indices, re-run `pytest -v`
to confirm everything still passes, and commit:

```bash
git add adapters/data_provider.py tests/test_data_provider.py
git commit -m "fix: correct KIS trade-tick field indices against live feed"
```

If the indices already match (no fix needed), skip the commit — this task ends
with just the manual confirmation in Step 2.
