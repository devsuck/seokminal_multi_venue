# KIS Daily Bar Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull daily (일봉) price history for Samsung Electronics (`005930`) from the
Korea Investment & Securities (KIS) Open API using a real-account app key, and write it
into a local Nautilus `ParquetDataCatalog` as a proper `Equity` instrument plus `Bar`
data.

**Architecture:** A synchronous `requests`-based KIS client (`backends/kis/`) fetches an
OAuth2 token and paginated daily-price rows. A pure-function mapping layer
(`adapters/data_provider.py`) converts KIS's raw JSON rows and instrument metadata into
Nautilus domain types (`Equity`, `Bar`) with no network or I/O dependencies, so it's
unit-testable with fixtures. An entry-point script (`data_ingestion.py`) wires these
together and writes to the catalog.

**Tech Stack:** Python 3.11+, `nautilus_trader` (v1.228.0, already installed),
`requests`, `python-dotenv`, `pytest`.

## Global Constraints

- Real (실전) KIS account only for this sub-project — read-only market-data calls,
  no order placement. Domain: `https://openapi.koreainvestment.com:9443`.
- Synchronous `requests`, not async — this is a one-shot batch script.
- Single instrument only: `005930.XKRX`. No multi-symbol support yet.
- Daily bars (일봉) only, via
  `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice`.
- KIS caps each response at 100 rows — pagination is required for ranges longer than
  ~100 trading days.
- No real credentials in code or tests. Tests use fixtures; the live script reads
  `KIS_APP_KEY` / `KIS_APP_SECRET` from environment via `.env`.

---

### Task 1: Project scaffolding and dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `backends/__init__.py`
- Create: `backends/kis/__init__.py`
- Create: `adapters/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: a `pip install -e .` (or `uv pip install -e .`) -able project with
  `requests`, `python-dotenv`, `nautilus_trader`, `pytest` as dependencies, importable
  as `backends.kis.*` and `adapters.*` from the repo root.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "nautilus-multi-venue"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "nautilus_trader",
    "requests>=2.31",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.env.example`**

```
KIS_APP_KEY=your-app-key-here
KIS_APP_SECRET=your-app-secret-here
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
catalog/
.venv/
*.egg-info/
```

- [ ] **Step 4: Create empty package init files**

```bash
mkdir -p backends/kis adapters tests
touch backends/__init__.py backends/kis/__init__.py adapters/__init__.py tests/__init__.py
```

- [ ] **Step 5: Install the project in editable mode**

Run: `cd ~/nautilus-multi-venue && pip install -e ".[dev]"`
Expected: install succeeds (nautilus_trader is already installed globally per earlier
check, so this should mostly install `requests`, `python-dotenv`, `pytest`).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example .gitignore backends adapters tests
git commit -m "chore: scaffold project structure and dependencies"
```

---

### Task 2: KIS OAuth2 token client

**Files:**
- Create: `backends/kis/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `requests` library; env vars `KIS_APP_KEY`, `KIS_APP_SECRET`.
- Produces: `class KISAuth` with constructor `KISAuth(app_key: str, app_secret: str,
  base_url: str = "https://openapi.koreainvestment.com:9443", session:
  requests.Session | None = None)` and method `get_access_token(self) -> str`. Caches
  the token in `self._token` and its expiry in `self._expires_at` (a `float` unix
  timestamp); refreshes automatically when within 60 seconds of expiry or unset.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auth.py
import time
from unittest.mock import MagicMock

import pytest

from backends.kis.auth import KISAuth


def _mock_session(token: str = "tok123", expires_in: int = 86400) -> MagicMock:
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": expires_in,
    }
    response.raise_for_status.return_value = None
    session.post.return_value = response
    return session


def test_get_access_token_fetches_and_returns_token():
    session = _mock_session(token="abc")
    auth = KISAuth(app_key="key", app_secret="secret", session=session)

    token = auth.get_access_token()

    assert token == "abc"
    session.post.assert_called_once()
    call_kwargs = session.post.call_args.kwargs
    assert call_kwargs["json"]["appkey"] == "key"
    assert call_kwargs["json"]["appsecret"] == "secret"
    assert call_kwargs["json"]["grant_type"] == "client_credentials"


def test_get_access_token_reuses_cached_token():
    session = _mock_session(token="abc")
    auth = KISAuth(app_key="key", app_secret="secret", session=session)

    first = auth.get_access_token()
    second = auth.get_access_token()

    assert first == second == "abc"
    session.post.assert_called_once()


def test_get_access_token_refreshes_when_near_expiry():
    session = _mock_session(token="abc", expires_in=86400)
    auth = KISAuth(app_key="key", app_secret="secret", session=session)
    auth.get_access_token()

    auth._expires_at = time.time() + 10  # within the 60s refresh window

    session.post.return_value.json.return_value["access_token"] = "def"
    second = auth.get_access_token()

    assert second == "def"
    assert session.post.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backends.kis.auth'`

- [ ] **Step 3: Implement `backends/kis/auth.py`**

```python
# backends/kis/auth.py
import time

import requests


class KISAuth:
    """Fetches and caches a KIS OAuth2 access token."""

    REFRESH_MARGIN_SECONDS = 60

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        base_url: str = "https://openapi.koreainvestment.com:9443",
        session: requests.Session | None = None,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base_url = base_url
        self._session = session or requests.Session()
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_access_token(self) -> str:
        if self._token is not None and time.time() < self._expires_at - self.REFRESH_MARGIN_SECONDS:
            return self._token
        return self._fetch_token()

    def _fetch_token(self) -> str:
        response = self._session.post(
            f"{self._base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._expires_at = time.time() + payload["expires_in"]
        return self._token
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backends/kis/auth.py tests/test_auth.py
git commit -m "feat: add KIS OAuth2 token client with caching"
```

---

### Task 3: KIS daily price client with pagination

**Files:**
- Create: `backends/kis/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `backends.kis.auth.KISAuth.get_access_token() -> str` (from Task 2).
- Produces: `class KISClient` with constructor `KISClient(app_key: str, app_secret:
  str, auth: KISAuth | None = None, base_url: str =
  "https://openapi.koreainvestment.com:9443", session: requests.Session | None = None,
  request_delay_seconds: float = 0.05)` and method
  `get_daily_price(self, code: str, start: str, end: str) -> list[dict]` where `start`/
  `end` are `"YYYYMMDD"` strings. Returns rows oldest-to-newest, each a dict with keys
  `stck_bsop_date`, `stck_oprc`, `stck_hgpr`, `stck_lwpr`, `stck_clpr`, `acml_vol`
  (KIS's native field names — mapping to Nautilus types happens in Task 4).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_client.py
from unittest.mock import MagicMock

from backends.kis.client import KISClient


def _row(date: str, close: str = "70000") -> dict:
    return {
        "stck_bsop_date": date,
        "stck_oprc": "69500",
        "stck_hgpr": "70500",
        "stck_lwpr": "69000",
        "stck_clpr": close,
        "acml_vol": "1000000",
    }


def _mock_response(rows: list[dict]) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"output2": rows, "rt_cd": "0"}
    response.raise_for_status.return_value = None
    return response


def test_get_daily_price_single_page_returns_rows_oldest_first():
    session = MagicMock()
    # KIS returns newest-first; client must reverse to oldest-first.
    rows_newest_first = [_row("20240103"), _row("20240102"), _row("20240101")]
    session.get.return_value = _mock_response(rows_newest_first)
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_price("005930", "20240101", "20240103")

    assert [r["stck_bsop_date"] for r in result] == ["20240101", "20240102", "20240103"]
    session.get.assert_called_once()
    call_kwargs = session.get.call_args.kwargs
    assert call_kwargs["headers"]["authorization"] == "Bearer tok"
    assert call_kwargs["headers"]["appkey"] == "key"
    assert call_kwargs["params"]["FID_INPUT_ISCD"] == "005930"


def test_get_daily_price_paginates_when_page_is_full(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    session = MagicMock()
    full_page = [_row(f"2024{(100 - i) // 4 + 1:02d}{(100 - i) % 28 + 1:02d}") for i in range(100)]
    second_page = [_row("20231201")]
    session.get.side_effect = [
        _mock_response(full_page),
        _mock_response(second_page),
    ]
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_price("005930", "20231201", "20240331")

    assert session.get.call_count == 2
    assert len(result) == 101


def test_get_daily_price_skips_blank_rows():
    session = MagicMock()
    rows = [_row("20240101"), {"stck_bsop_date": "", "stck_oprc": "", "stck_hgpr": "",
                                "stck_lwpr": "", "stck_clpr": "", "acml_vol": ""}]
    session.get.return_value = _mock_response(rows)
    auth = MagicMock()
    auth.get_access_token.return_value = "tok"

    client = KISClient(app_key="key", app_secret="secret", auth=auth, session=session)
    result = client.get_daily_price("005930", "20240101", "20240101")

    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backends.kis.client'`

- [ ] **Step 3: Implement `backends/kis/client.py`**

```python
# backends/kis/client.py
import time

import requests

from backends.kis.auth import KISAuth

DAILY_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
DAILY_PRICE_TR_ID = "FHKST03010100"
PAGE_SIZE = 100


class KISClient:
    """Synchronous client for KIS domestic-stock market-data endpoints."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        auth: KISAuth | None = None,
        base_url: str = "https://openapi.koreainvestment.com:9443",
        session: requests.Session | None = None,
        request_delay_seconds: float = 0.05,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base_url = base_url
        self._session = session or requests.Session()
        self._auth = auth or KISAuth(app_key, app_secret, base_url, self._session)
        self._request_delay_seconds = request_delay_seconds

    def get_daily_price(self, code: str, start: str, end: str) -> list[dict]:
        all_rows: list[dict] = []
        window_end = end

        while True:
            page = self._fetch_page(code, start, window_end)
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

    def _fetch_page(self, code: str, start: str, end: str) -> list[dict]:
        token = self._auth.get_access_token()
        response = self._session.get(
            f"{self._base_url}{DAILY_PRICE_PATH}",
            headers={
                "authorization": f"Bearer {token}",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
                "tr_id": DAILY_PRICE_TR_ID,
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": start,
                "FID_INPUT_DATE_2": end,
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("output2", [])
        non_blank = [row for row in rows if row.get("stck_bsop_date")]
        non_blank.sort(key=lambda row: row["stck_bsop_date"])
        return non_blank


def _previous_day(date_str: str) -> str:
    import datetime as dt

    day = dt.datetime.strptime(date_str, "%Y%m%d")
    return (day - dt.timedelta(days=1)).strftime("%Y%m%d")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backends/kis/client.py tests/test_client.py
git commit -m "feat: add KIS daily price client with pagination"
```

---

### Task 4: Mapping KIS rows to Nautilus Instrument and Bar

**Files:**
- Create: `adapters/data_provider.py`
- Test: `tests/test_data_provider.py`

**Interfaces:**
- Consumes: raw KIS row dicts as returned by `KISClient.get_daily_price` (Task 3),
  with keys `stck_bsop_date` (`"YYYYMMDD"`), `stck_oprc`, `stck_hgpr`, `stck_lwpr`,
  `stck_clpr`, `acml_vol` (all numeric strings).
- Produces:
  - `build_xkrx_equity(code: str) -> Equity` — `InstrumentId` is
    `f"{code}.XKRX"`, `Symbol(code)`, `Currency.from_str("KRW")`, `price_precision=0`,
    `price_increment=Price.from_str("1")`, `lot_size=Quantity.from_int(1)`.
  - `BARTYPE_FOR(instrument_id: InstrumentId) -> BarType` returning
    `BarType.from_str(f"{instrument_id}-1-DAY-LAST-EXTERNAL")`.
  - `map_kis_daily_bar(row: dict, bar_type: BarType, price_precision: int) -> Bar`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_data_provider.py
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

from adapters.data_provider import bar_type_for, build_xkrx_equity, map_kis_daily_bar


def test_build_xkrx_equity_has_expected_fields():
    equity = build_xkrx_equity("005930")

    assert equity.id == InstrumentId.from_str("005930.XKRX")
    assert str(equity.quote_currency) == "KRW"
    assert equity.price_precision == 0
    assert equity.lot_size.as_double() == 1.0


def test_bar_type_for_builds_daily_external_bar_type():
    instrument_id = InstrumentId.from_str("005930.XKRX")

    bar_type = bar_type_for(instrument_id)

    assert bar_type == BarType.from_str("005930.XKRX-1-DAY-LAST-EXTERNAL")


def test_map_kis_daily_bar_converts_row_to_bar():
    bar_type = bar_type_for(InstrumentId.from_str("005930.XKRX"))
    row = {
        "stck_bsop_date": "20240102",
        "stck_oprc": "69500",
        "stck_hgpr": "70500",
        "stck_lwpr": "69000",
        "stck_clpr": "70000",
        "acml_vol": "1000000",
    }

    bar = map_kis_daily_bar(row, bar_type, price_precision=0)

    assert bar.bar_type == bar_type
    assert bar.open.as_double() == 69500.0
    assert bar.high.as_double() == 70500.0
    assert bar.low.as_double() == 69000.0
    assert bar.close.as_double() == 70000.0
    assert bar.volume.as_double() == 1_000_000.0
    # 2024-01-02 00:00:00 UTC in nanoseconds
    assert bar.ts_event == 1704153600000000000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_data_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adapters.data_provider'`

- [ ] **Step 3: Implement `adapters/data_provider.py`**

```python
# adapters/data_provider.py
import datetime as dt

from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import KRW
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity


def build_xkrx_equity(code: str) -> Equity:
    now_ns = dt_to_unix_nanos(dt.datetime.now(dt.timezone.utc))
    return Equity(
        instrument_id=InstrumentId.from_str(f"{code}.XKRX"),
        raw_symbol=Symbol(code),
        currency=KRW,
        price_precision=0,
        price_increment=Price.from_str("1"),
        lot_size=Quantity.from_int(1),
        ts_event=now_ns,
        ts_init=now_ns,
    )


def bar_type_for(instrument_id: InstrumentId) -> BarType:
    return BarType.from_str(f"{instrument_id}-1-DAY-LAST-EXTERNAL")


def map_kis_daily_bar(row: dict, bar_type: BarType, price_precision: int) -> Bar:
    event_date = dt.datetime.strptime(row["stck_bsop_date"], "%Y%m%d").replace(
        tzinfo=dt.timezone.utc
    )
    ts_event = dt_to_unix_nanos(event_date)

    return Bar(
        bar_type=bar_type,
        open=Price(float(row["stck_oprc"]), price_precision),
        high=Price(float(row["stck_hgpr"]), price_precision),
        low=Price(float(row["stck_lwpr"]), price_precision),
        close=Price(float(row["stck_clpr"]), price_precision),
        volume=Quantity(float(row["acml_vol"]), 0),
        ts_event=ts_event,
        ts_init=ts_event,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_provider.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add adapters/data_provider.py tests/test_data_provider.py
git commit -m "feat: map KIS daily bar rows to Nautilus Equity and Bar types"
```

---

### Task 5: Ingestion entry-point script

**Files:**
- Create: `data_ingestion.py`
- Test: `tests/test_data_ingestion.py`

**Interfaces:**
- Consumes: `KISClient.get_daily_price` (Task 3), `build_xkrx_equity`,
  `bar_type_for`, `map_kis_daily_bar` (Task 4).
- Produces: `run_ingestion(code: str, start: str, end: str, catalog_path: str,
  client: KISClient) -> int` (returns number of bars written) and a `main()` CLI
  entry point reading `KIS_APP_KEY`/`KIS_APP_SECRET` from env via `python-dotenv`,
  with `code`/`start`/`end`/`catalog_path` as CLI args (defaulting to `005930`,
  one year back from today, and `./catalog`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_ingestion.py
import tempfile
from unittest.mock import MagicMock

from nautilus_trader.persistence.catalog import ParquetDataCatalog

from data_ingestion import run_ingestion


def test_run_ingestion_writes_instrument_and_bars_to_catalog():
    client = MagicMock()
    client.get_daily_price.return_value = [
        {
            "stck_bsop_date": "20240102",
            "stck_oprc": "69500",
            "stck_hgpr": "70500",
            "stck_lwpr": "69000",
            "stck_clpr": "70000",
            "acml_vol": "1000000",
        },
        {
            "stck_bsop_date": "20240103",
            "stck_oprc": "70000",
            "stck_hgpr": "71000",
            "stck_lwpr": "69800",
            "stck_clpr": "70800",
            "acml_vol": "900000",
        },
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        written = run_ingestion(
            code="005930",
            start="20240101",
            end="20240103",
            catalog_path=tmp_dir,
            client=client,
        )

        assert written == 2

        catalog = ParquetDataCatalog(tmp_dir)
        instruments = catalog.instruments()
        assert len(instruments) == 1
        assert str(instruments[0].id) == "005930.XKRX"

        bars = catalog.bars()
        assert len(bars) == 2
        assert bars[0].close.as_double() == 70000.0
        assert bars[1].close.as_double() == 70800.0

    client.get_daily_price.assert_called_once_with("005930", "20240101", "20240103")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_ingestion.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_ingestion'`

- [ ] **Step 3: Implement `data_ingestion.py`**

```python
# data_ingestion.py
import argparse
import datetime as dt
import os

from dotenv import load_dotenv
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for, build_xkrx_equity, map_kis_daily_bar
from backends.kis.client import KISClient


def run_ingestion(code: str, start: str, end: str, catalog_path: str, client: KISClient) -> int:
    instrument = build_xkrx_equity(code)
    bar_type = bar_type_for(instrument.id)

    rows = client.get_daily_price(code, start, end)
    bars = [
        map_kis_daily_bar(row, bar_type, instrument.price_precision)
        for row in rows
    ]

    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([instrument])
    catalog.write_data(bars)

    return len(bars)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Ingest KIS daily bars into a ParquetDataCatalog")
    parser.add_argument("--code", default="005930")
    parser.add_argument("--start", default=(dt.date.today() - dt.timedelta(days=365)).strftime("%Y%m%d"))
    parser.add_argument("--end", default=dt.date.today().strftime("%Y%m%d"))
    parser.add_argument("--catalog-path", default="./catalog")
    args = parser.parse_args()

    app_key = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    client = KISClient(app_key=app_key, app_secret=app_secret)

    written = run_ingestion(args.code, args.start, args.end, args.catalog_path, client)
    print(f"Wrote {written} bars for {args.code} ({args.start}-{args.end}) to {args.catalog_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_data_ingestion.py -v`
Expected: 1 passed

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests across `test_auth.py`, `test_client.py`, `test_data_provider.py`,
`test_data_ingestion.py` pass.

- [ ] **Step 6: Commit**

```bash
git add data_ingestion.py tests/test_data_ingestion.py
git commit -m "feat: add KIS daily-bar ingestion entry-point script"
```

---

### Task 6: Manual end-to-end verification with real credentials

**Files:**
- Modify: none (manual verification step, no code changes)

**Interfaces:**
- Consumes: `main()` from `data_ingestion.py` (Task 5), real `.env` file (not
  committed).

- [ ] **Step 1: Create local `.env` with real credentials**

```bash
cp .env.example .env
# then manually edit .env to fill in real KIS_APP_KEY and KIS_APP_SECRET
```

- [ ] **Step 2: Run the ingestion script for a short, recent date range**

Run: `python data_ingestion.py --code 005930 --start 20240601 --end 20240630 --catalog-path ./catalog`
Expected: prints `Wrote N bars for 005930 (20240601-20240630) to ./catalog` with `N`
roughly equal to the number of trading days in June 2024 (around 19-20).

- [ ] **Step 3: Inspect the catalog to confirm the round trip**

```bash
python3 -c "
from nautilus_trader.persistence.catalog import ParquetDataCatalog
catalog = ParquetDataCatalog('./catalog')
print(catalog.instruments())
bars = catalog.bars()
print(len(bars), bars[0], bars[-1])
"
```

Expected: one `Equity` instrument for `005930.XKRX`, and a list of `Bar` objects
ordered oldest-to-newest matching the requested date range.

- [ ] **Step 4: Confirm `.env` is not tracked by git**

Run: `git status`
Expected: `.env` does not appear (it's covered by `.gitignore` from Task 1).

No commit for this task — it's a manual verification checkpoint only.
