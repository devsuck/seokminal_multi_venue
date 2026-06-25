# Dashboard-Backend API Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI REST server (`api_server/`) exposing three GET
endpoints — `/bars`, `/backtest`, `/correlation` — that query the existing
`ParquetDataCatalog`, `backtest_runner.run_backtest`, and
`correlation_analysis.corr_matrix` modules on every request, with no new
analysis logic and no persistence layer.

**Architecture:** One FastAPI app (`api_server/main.py`) with three route
handlers. Each handler converts query params into the existing functions'
exact argument shapes (reusing `adapters.data_provider.bar_type_for` for
bar-type derivation and `nautilus_trader.core.datetime.dt_to_unix_nanos`
for date conversion), calls the function directly, and maps `ValueError`
to HTTP 400. Pydantic models define response shapes only (no request
body — query params only).

**Tech Stack:** FastAPI, Uvicorn, Pydantic (FastAPI's built-in), pytest +
FastAPI's `TestClient`.

## Global Constraints

- Headless, API-first: no UI library dependency in this package (per
  Phase 1 standing constraint #1).
- No caching, no database, no background jobs — every request re-runs
  the underlying function synchronously (per spec's execution-model
  decision, Option A).
- No changes to `backtest_runner/`, `correlation_analysis/`, or
  `adapters/data_provider.py` — this plan only adds new files under
  `api_server/` and `tests/`.
- Catalog path is the existing `./catalog` directory, hardcoded as a
  module constant (matches existing script patterns, e.g.
  `place_test_order.py`).
- Unhandled exceptions outside the explicit `ValueError` mapping
  propagate as FastAPI's default 500 (no blanket try/except).

---

### Task 1: Project setup + `/bars` endpoint

**Files:**
- Create: `api_server/__init__.py` (empty)
- Create: `api_server/main.py`
- Modify: `pyproject.toml` (add `fastapi`, `uvicorn`, `httpx` deps)
- Test: `tests/test_api_server.py`

**Interfaces:**
- Consumes: `adapters.data_provider.bar_type_for(instrument_id:
  InstrumentId) -> BarType`; `nautilus_trader.core.datetime.dt_to_unix_nanos(dt.datetime) -> int`;
  `nautilus_trader.persistence.catalog.ParquetDataCatalog(path).bars(bar_types: list[str]) -> list[Bar]`.
- Produces: `api_server.main.app` (FastAPI instance, importable by
  `TestClient(app)`); `api_server.main.CATALOG_PATH` (module constant,
  `"./catalog"`); `api_server.main.date_to_ns(date_str: str) -> int`
  (helper, parses `YYYY-MM-DD` to UTC-midnight nanoseconds — used by
  Tasks 2 and 3 too).

- [ ] **Step 1: Add FastAPI dependencies to `pyproject.toml`**

Edit the `dependencies` list in `pyproject.toml`:

```toml
dependencies = [
    "nautilus_trader",
    "requests>=2.31",
    "python-dotenv>=1.0",
    "ib_async>=2.1.0",
    "fastapi>=0.110",
    "uvicorn>=0.29",
]
```

Edit the `dev` optional-dependencies list to add `httpx` (required by
FastAPI's `TestClient`):

```toml
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]
```

Edit `[tool.setuptools.packages.find]` to include the new package:

```toml
[tool.setuptools.packages.find]
include = ["backends*", "adapters*", "tests*", "api_server*"]
```

Run: `pip install -e ".[dev]"`
Expected: installs without error, `fastapi`/`uvicorn`/`httpx` importable.

- [ ] **Step 2: Write the failing test for `/bars`**

Create `tests/test_api_server.py`:

```python
from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app)


def test_bars_happy_path_returns_known_instrument_data():
    response = client.get(
        "/bars",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["instrument_id"] == "AAPL.NASDAQ"
    assert len(body["bars"]) > 0
    first_bar = body["bars"][0]
    assert set(first_bar.keys()) == {
        "ts_event",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }


def test_bars_unknown_instrument_returns_400():
    response = client.get(
        "/bars",
        params={
            "instrument_id": "NOPE.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 400
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_api_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api_server'`

- [ ] **Step 4: Write `api_server/__init__.py` and `api_server/main.py`**

Create `api_server/__init__.py` (empty file).

Create `api_server/main.py`:

```python
import datetime as dt

from fastapi import FastAPI, HTTPException, Query
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from pydantic import BaseModel

from adapters.data_provider import bar_type_for

CATALOG_PATH = "./catalog"

app = FastAPI(title="Nautilus Multi-Venue Dashboard API")


def date_to_ns(date_str: str) -> int:
    parsed = dt.date.fromisoformat(date_str)
    event_date = dt.datetime.combine(parsed, dt.time.min, tzinfo=dt.timezone.utc)
    return int(event_date.timestamp() * 1_000_000_000)


class BarOut(BaseModel):
    ts_event: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarsResponse(BaseModel):
    instrument_id: str
    bars: list[BarOut]


@app.get("/bars", response_model=BarsResponse)
def get_bars(
    instrument_id: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
) -> BarsResponse:
    start_ns = date_to_ns(start)
    end_ns = date_to_ns(end)

    catalog = ParquetDataCatalog(CATALOG_PATH)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))

    try:
        all_bars = catalog.bars(bar_types=[bar_type_str])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    bars = [b for b in all_bars if start_ns <= b.ts_event <= end_ns]
    if not bars:
        raise HTTPException(
            status_code=400,
            detail=f"no bars found for {instrument_id!r} in range [{start}, {end}]",
        )

    return BarsResponse(
        instrument_id=instrument_id,
        bars=[
            BarOut(
                ts_event=b.ts_event,
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in bars
        ],
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_api_server.py -v`
Expected: both `test_bars_*` tests PASS (requires `./catalog` to already
contain `AAPL.NASDAQ` data from sub-project 8 — confirmed present per
progress ledger).

- [ ] **Step 6: Commit**

```bash
git add api_server/ pyproject.toml tests/test_api_server.py
git commit -m "feat: add FastAPI server with /bars endpoint"
```

---

### Task 2: `/backtest` endpoint

**Files:**
- Modify: `api_server/main.py`
- Test: `tests/test_api_server.py`

**Interfaces:**
- Consumes: `api_server.main.date_to_ns` (Task 1);
  `backtest_runner.runner.run_backtest(instrument_id: str, bar_type_str:
  str, start_ns: int, end_ns: int, catalog_path: str, spawn_rules_json:
  list[dict], starting_balance: float = 100_000) -> dict` (returns
  `{instrument_id, bar_count, sharpe_ratio, max_drawdown, total_pnl,
  total_pnl_pct}`).
- Produces: `GET /backtest` route on `api_server.main.app`.

- [ ] **Step 1: Write the failing test for `/backtest`**

Append to `tests/test_api_server.py`:

```python
def test_backtest_happy_path_returns_all_metric_keys():
    response = client.get(
        "/backtest",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
            "strategy": "ema_cross",
            "fast": 10,
            "slow": 20,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "sharpe_ratio",
        "max_drawdown",
        "total_pnl",
        "total_pnl_pct",
        "bar_count",
    }


def test_backtest_unsupported_strategy_returns_400():
    response = client.get(
        "/backtest",
        params={
            "instrument_id": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2026-12-31",
            "strategy": "not_a_real_strategy",
            "fast": 10,
            "slow": 20,
        },
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_server.py -v`
Expected: FAIL with `404 Not Found` for the `/backtest` route (route
doesn't exist yet).

- [ ] **Step 3: Add the `/backtest` route to `api_server/main.py`**

Add these imports at the top of `api_server/main.py`:

```python
from backtest_runner.runner import run_backtest
```

Add this response model and route to `api_server/main.py`:

```python
class BacktestResponse(BaseModel):
    sharpe_ratio: float | None
    max_drawdown: float | None
    total_pnl: float | None
    total_pnl_pct: float | None
    bar_count: int


SUPPORTED_STRATEGIES = {"ema_cross"}


@app.get("/backtest", response_model=BacktestResponse)
def get_backtest(
    instrument_id: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    strategy: str = Query(...),
    fast: int = Query(10),
    slow: int = Query(20),
    trade_size: int = Query(10),
) -> BacktestResponse:
    if strategy not in SUPPORTED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported strategy {strategy!r}, expected one of {SUPPORTED_STRATEGIES}",
        )

    start_ns = date_to_ns(start)
    end_ns = date_to_ns(end)
    bar_type_str = str(bar_type_for(InstrumentId.from_str(instrument_id)))

    spawn_rules_json = [
        {
            "condition": {"combinator": "AND", "conditions": []},
            "strategy": {
                "class": "backtest_runner.ema_cross_flat:EMACrossFlat",
                "params": {
                    "instrument_id": instrument_id,
                    "bar_type": bar_type_str,
                    "trade_size": trade_size,
                    "fast_ema_period": fast,
                    "slow_ema_period": slow,
                    "request_bars": False,
                    "subscribe_trade_ticks": False,
                },
            },
        }
    ]

    try:
        report = run_backtest(
            instrument_id=instrument_id,
            bar_type_str=bar_type_str,
            start_ns=start_ns,
            end_ns=end_ns,
            catalog_path=CATALOG_PATH,
            spawn_rules_json=spawn_rules_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BacktestResponse(
        sharpe_ratio=report["sharpe_ratio"],
        max_drawdown=report["max_drawdown"],
        total_pnl=report["total_pnl"],
        total_pnl_pct=report["total_pnl_pct"],
        bar_count=report["bar_count"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_server.py -v`
Expected: all 4 tests so far PASS.

- [ ] **Step 5: Commit**

```bash
git add api_server/main.py tests/test_api_server.py
git commit -m "feat: add /backtest endpoint to dashboard API"
```

---

### Task 3: `/correlation` endpoint

**Files:**
- Modify: `api_server/main.py`
- Test: `tests/test_api_server.py`

**Interfaces:**
- Consumes: `api_server.main.date_to_ns` (Task 1);
  `correlation_analysis.correlation.corr_matrix(instrument_ids: list[str],
  bar_type_strs: list[str], start_ns: int, end_ns: int, catalog_path:
  str) -> dict[tuple[str, str], float]`.
- Produces: `GET /correlation` route on `api_server.main.app`.

- [ ] **Step 1: Write the failing test for `/correlation`**

Append to `tests/test_api_server.py`:

```python
def test_correlation_happy_path_returns_known_pair_value():
    response = client.get(
        "/correlation",
        params={
            "instrument_ids": "005930.XKRX,000660.XKRX",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 200
    body = response.json()
    pairs = {(p["a"], p["b"]): p["correlation"] for p in body["pairs"]}
    assert pairs[("005930.XKRX", "000660.XKRX")] == pytest.approx(0.756, abs=0.01)


def test_correlation_single_instrument_returns_400():
    response = client.get(
        "/correlation",
        params={
            "instrument_ids": "005930.XKRX",
            "start": "2024-01-01",
            "end": "2026-12-31",
        },
    )
    assert response.status_code == 400
```

Add `import pytest` to the top of `tests/test_api_server.py` if not
already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_server.py -v`
Expected: FAIL with `404 Not Found` for the `/correlation` route.

- [ ] **Step 3: Add the `/correlation` route to `api_server/main.py`**

Add this import at the top of `api_server/main.py`:

```python
from correlation_analysis.correlation import corr_matrix
```

Add this response model and route to `api_server/main.py`:

```python
class CorrelationPair(BaseModel):
    a: str
    b: str
    correlation: float


class CorrelationResponse(BaseModel):
    pairs: list[CorrelationPair]


@app.get("/correlation", response_model=CorrelationResponse)
def get_correlation(
    instrument_ids: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
) -> CorrelationResponse:
    ids = instrument_ids.split(",")
    bar_type_strs = [
        str(bar_type_for(InstrumentId.from_str(instrument_id))) for instrument_id in ids
    ]
    start_ns = date_to_ns(start)
    end_ns = date_to_ns(end)

    try:
        matrix = corr_matrix(
            instrument_ids=ids,
            bar_type_strs=bar_type_strs,
            start_ns=start_ns,
            end_ns=end_ns,
            catalog_path=CATALOG_PATH,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    seen: set[tuple[str, str]] = set()
    pairs = []
    for (a, b), correlation in matrix.items():
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        pairs.append(CorrelationPair(a=key[0], b=key[1], correlation=correlation))

    return CorrelationResponse(pairs=pairs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_server.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `pytest -v`
Expected: all tests pass (previous count + 6 new `api_server` tests, no
existing test broken).

- [ ] **Step 6: Commit**

```bash
git add api_server/main.py tests/test_api_server.py
git commit -m "feat: add /correlation endpoint to dashboard API"
```

---

### Task 4: Manual end-to-end verification

**Files:** none (verification only, no code changes expected).

**Interfaces:** none.

- [ ] **Step 1: Start the server**

Run: `uvicorn api_server.main:app --reload --port 8000`
Expected: server starts, logs `Uvicorn running on http://127.0.0.1:8000`.

- [ ] **Step 2: Manually hit all three endpoints**

```bash
curl "http://127.0.0.1:8000/bars?instrument_id=AAPL.NASDAQ&start=2024-01-01&end=2026-12-31"
curl "http://127.0.0.1:8000/backtest?instrument_id=AAPL.NASDAQ&start=2024-01-01&end=2026-12-31&strategy=ema_cross&fast=10&slow=20"
curl "http://127.0.0.1:8000/correlation?instrument_ids=005930.XKRX,000660.XKRX&start=2024-01-01&end=2026-12-31"
```

Expected: all three return `200` with non-empty JSON bodies matching the
shapes defined in Tasks 1-3.

- [ ] **Step 3: Check the auto-generated OpenAPI docs**

Open `http://127.0.0.1:8000/docs` in a browser.
Expected: Swagger UI loads, all three endpoints listed with correct
query parameters.

- [ ] **Step 4: Update the progress ledger**

Append to `.superpowers/sdd/progress.md`:

```
--- Sub-project 11: dashboard-backend API server (spec 005536a, plan <this commit>) ---
Manual end-to-end verification: complete (date, real ./catalog data).
All three endpoints (/bars, /backtest, /correlation) verified via curl
and /docs Swagger UI. Sub-project 11 fully complete.
```

(Fill in the actual date and plan commit hash when this step runs.)

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs: record sub-project 11 manual verification"
```
