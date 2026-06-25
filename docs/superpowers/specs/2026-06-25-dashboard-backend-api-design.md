# Dashboard-Backend API Server (Sub-project 11)

**Goal:** A FastAPI REST server that exposes read/query access to the
three existing engine modules — `ParquetDataCatalog` bar data,
`backtest_runner.run_backtest`, and `correlation_analysis.corr_matrix` —
over plain HTTP GET endpoints. This is the dashboard-backend half of
Phase 3 (the correlation/factor-exposure half was already completed in
sub-project 10). It introduces no new analysis logic; it is purely a
query/transport layer in front of work that already exists, satisfying
the Phase 1 standing constraint of headless, API-first access for the
eventual React/Next.js frontend.

## Scope

In scope:
- A new top-level package, `api_server/`, parallel to the existing
  `backtest_runner/`, `correlation_analysis/`, etc.
- Three GET endpoints, all query-string parameterized (no request body):
  1. `GET /bars` — daily bars for one instrument over a date range, from
     `ParquetDataCatalog.bars()`.
  2. `GET /backtest` — runs `backtest_runner.run_backtest` for one
     instrument/strategy/date-range combination and returns its metrics
     dict (`sharpe_ratio`, `max_drawdown`, `total_pnl`, `total_pnl_pct`,
     `bar_count`).
  3. `GET /correlation` — runs `correlation_analysis.corr_matrix` for a
     comma-separated list of instruments over a date range and returns
     the pairwise correlation matrix.
- Synchronous, on-request execution. No caching, no job queue, no
  database. Every request re-runs the underlying function against the
  catalog directly (sub-9/sub-10 measured these at ~200-300ms for the
  current 4-instrument/250-bar catalog, which is acceptable for this
  scope).
- Thin request-shaping only: deriving the `bar_type_str` /
  `spawn_rules_json` arguments that `run_backtest` and `corr_matrix`
  require internally, from simpler query parameters. No changes to the
  underlying module signatures.
- Pydantic response models for all three endpoints (FastAPI's automatic
  request-side query-param validation is sufficient; no separate request
  models needed since there's no body).
- Explicit HTTP error mapping: catalog/module `ValueError`s (e.g. unknown
  instrument, empty result, mismatched list lengths) become `400`;
  legitimately-empty results (no error raised, just nothing found) are
  not expected to occur given current `ValueError`-on-empty behavior in
  the underlying functions, so no separate `404` case is needed.
- Tests: FastAPI `TestClient` covering one happy path per endpoint
  against the real `./catalog` data plus one error case per endpoint
  (e.g. unknown instrument).

Out of scope (deferred to later sub-projects):
- Authentication, CORS, rate limiting — local development only at this
  stage.
- Caching, persistence of computed results, background job execution
  (Option B from the execution-model discussion — explicit trigger +
  stored results). Revisit only if request latency becomes a real
  problem once the catalog grows.
- WebSocket / realtime streaming endpoints (Phase 1's `live_trade_stream*`
  modules are not wired into this API in this sub-project).
- The actual frontend (React/Next.js) — this sub-project is backend-only.
- POST/PUT endpoints for triggering bot config changes or live trading —
  out of scope until Phase 4 (agentic AI trading layer).

## Architecture

`api_server/main.py` constructs a single FastAPI `app` with three route
handlers. Each handler:
1. Parses/validates query params via the FastAPI parameter declaration
   (`Query(...)` for required params, defaults for optional ones like
   strategy parameters).
2. Builds the exact arguments the existing function needs (e.g.
   `bar_type_str = f"{instrument_id}-1-DAY-LAST-EXTERNAL"`,
   `spawn_rules_json = [{"strategy": "ema_cross", ...}]` from
   `strategy`/`fast`/`slow` query params).
3. Calls the existing function directly (no subprocess, no async wrapper
   needed since these functions are synchronous and fast).
4. Catches `ValueError` from the called function and re-raises as
   `fastapi.HTTPException(status_code=400, detail=str(e))`.
5. Returns the result coerced into its Pydantic response model.

Catalog path (`./catalog`) is a module-level constant in `api_server/`,
matching the hardcoded pattern already used in `backtest_runner` and
`correlation_analysis` call sites (e.g. `place_test_order.py`-style
scripts) — no new config system introduced.

### Endpoint Details

**`GET /bars?instrument_id=AAPL.NASDAQ&start=2026-01-01&end=2026-06-01`**
- `start`/`end` are `YYYY-MM-DD` dates, converted to UTC-midnight
  nanoseconds internally (same conversion already used in
  `data_ingestion_ib.py` for IB daily bars).
- Response: `{"instrument_id": str, "bars": [{"ts_event": int, "open":
  float, "high": float, "low": float, "close": float, "volume": float}]}`.

**`GET /backtest?instrument_id=AAPL.NASDAQ&start=...&end=...&strategy=ema_cross&fast=10&slow=20`**
- `strategy` is currently always `ema_cross` (the only strategy
  `run_backtest`'s `EMACrossFlat` wiring supports today); the param
  exists for forward-compatibility but only `"ema_cross"` is accepted in
  this sub-project (anything else is a `400`).
- `fast`/`slow` map directly into the single spawn rule's
  `strategy.params`.
- Response: `{"sharpe_ratio": float, "max_drawdown": float, "total_pnl":
  float, "total_pnl_pct": float, "bar_count": int}` — the exact dict
  `run_backtest` already returns, passed through unchanged.

**`GET /correlation?instrument_ids=005930.XKRX,000660.XKRX&start=...&end=...`**
- `instrument_ids` is a single comma-separated query param (not repeated
  params), split into a list server-side.
- `bar_type_strs` are derived the same way as `/bars`
  (`f"{id}-1-DAY-LAST-EXTERNAL"` per instrument) — not exposed as a
  separate param, since every instrument in the current catalog uses the
  same daily-bar convention.
- Response: pairwise matrix serialized as `{"pairs": [{"a": str, "b":
  str, "correlation": float}]}` (flat list, since JSON object keys can't
  be tuples — the function's `dict[tuple[str,str], float]` return value
  is flattened for the response).

## Error Handling

- Unknown/missing instrument in catalog → `400` with the underlying
  `ValueError` message passed through as `detail`.
- `strategy` param other than `"ema_cross"` → `400`.
- Malformed `start`/`end` date strings → FastAPI's built-in `422` for
  unparseable query params (no custom handling needed).
- Any other unhandled exception is not specifically caught — propagates
  as FastAPI's default `500`, consistent with "fail loud, don't paper
  over unexpected errors" already practiced in `backtest_runner` and
  `correlation_analysis`.

## Testing

`tests/test_api_server.py` using FastAPI's `TestClient` against the real
`./catalog` fixture data (the same 4-instrument catalog used by sub-9
and sub-10's manual verification):
- `/bars` happy path: known instrument, date range covering existing
  data, non-empty bar list returned.
- `/bars` error: unknown instrument → `400`.
- `/backtest` happy path: `AAPL.NASDAQ`, `ema_cross`, same params as
  sub-9's manual verification → response contains all 5 metric keys.
- `/backtest` error: unsupported `strategy` value → `400`.
- `/correlation` happy path: the same 2-instrument pair sub-10 verified
  (`005930.XKRX`/`000660.XKRX`) → response contains the matching
  correlation value (~0.756, allowing floating-point tolerance).
- `/correlation` error: single instrument_id (no comma) → `400` (matches
  `corr_matrix`'s existing "requires at least 2 instruments" check).
