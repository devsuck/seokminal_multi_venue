# Backtest Auto-Ingestion Adapter (P54)

> Governed by `docs/CONSTITUTION.md`, `docs/AGENTIC_RESEARCH_EVOLUTION.md`, and P53
> (`docs/research_data_pipeline.md`).
> **Integration over expansion** — this adapter creates NO new storage and NO new
> experiment/failure system. It wires the *real* backtest workflow into the existing
> P53 pipeline so a completed backtest **automatically becomes research memory**.
> **No trading. No execution. No capital allocation. Human decision stays mandatory.**

## Problem it fixes

P53 built the pipeline (`research_ingestion.ingest()`) and proved that a backtest *dict*
becomes memory. But it still had to be fed a **hand-written P53 schema**. The real
backtesters — `backtest_runner/runner.py`, `backtest_runner/simple_runner.py`,
`jarvis/agents/backtest.py` — emit their *own* result shapes and nothing mapped them.
So in practice the ledgers stayed empty.

P54 closes that last gap with one **thin adapter** + one **idempotent hook**.

## 1. Backtest completion point (single, not duplicated)

The "single point where a completed backtest result exists" is the **return dict** of the
existing runners — the adapter reads that dict; it never re-runs a backtest and never
duplicates an execution path.

| Producer | File · point | Shape |
|---|---|---|
| Nautilus engine | `backtest_runner/runner.py` → `run_backtest()` return (`return {...}`) | flat: `sharpe_ratio`, `max_drawdown`, `total_pnl_pct`, `volatility`, `win_rate`, `trades`, … |
| Pure-python | `backtest_runner/simple_runner.py` → `run_simple_backtest()` return | same flat shape |
| Agent loop | `jarvis/agents/backtest.py` → `run()` return | nested: `{strategy_id, metrics:{sharpe, ann_return, wf_first, wf_second, …}, provenance:{…}}` |

The runners are **frozen** — P54 does not modify them. The adapter lives on the research
side and *consumes* their output, keeping the dependency direction research → trading-output
(never trading → research, never an execution import).

## 2. The adapter — pure mapping (`jarvis/research_ingestion/backtest_adapter.py`)

`adapt(backtest_output, *, context=None) -> dict` renames/moves keys into the P53 schema.
It **computes nothing** and **writes nothing**:

```
backtest_runner output                     P53 schema (research_ingestion)
──────────────────────                     ───────────────────────────────
sharpe_ratio / metrics.sharpe        ──▶   metrics.sharpe
total_pnl_pct / ann_return / net     ──▶   metrics.return
max_drawdown                         ──▶   metrics.max_drawdown
volatility                           ──▶   metrics.volatility
wf_first  / walk_forward             ──▶   metrics.walk_forward
wf_second / out_of_sample            ──▶   metrics.out_of_sample
provenance.code_version              ──▶   strategy_version
strategy_id / instrument_id          ──▶   strategy_name (fallback)
provenance{…}                        ──▶   provenance (audit passthrough)
```

Metrics the raw backtest **cannot** produce — `walk_forward`, `out_of_sample`,
`cost_impact`, `parameter_stability`, `random_baseline` — come from the validation
harness (`research/validation`, `research/run_validation.py`) and are supplied via
`context["metrics"]`. Context **never overwrites** a value the backtest already produced.

If those validations are absent, ingestion still proceeds but the outcome is judged
**INCOMPLETE** — the gap is surfaced, never hidden.

Research metadata the backtest doesn't carry (hypothesis, universe, period, features,
entry/exit/risk rules) is also supplied through `context`.

## 3. The hook — automatic, idempotent (`ingest_backtest`)

```python
from jarvis.research_ingestion import ingest_backtest

# after a backtest completes (agent loop, notebook, or batch):
result = ingest_backtest(bt_output, context=ctx, now=ts, commit=True)
```

`ingest_backtest()` = `adapt()` → existing `ResearchIngestionEngine.ingest()`. It is the
**single entry point** for "backtest done → research memory." Because P53 dedups on
`backtest_hash`, calling it twice on the same result is a **no-op**
(`deduplicated=True`) — append-only, hash-chained, dedup preserved. `commit=False`
is a dry-run preview (judgement only, no writes).

## 4. Flow (agent → backtest → stored → memory → recall)

```
agent proposes spec ─▶ backtest_runner runs ─▶ completed result dict
                                                     │  ingest_backtest(result, context)
                                                     │    adapt() → P53 ingest()
   ┌─────────────────────────────────────────────────┼──────────────────────────────┐
   ├─▶ experiment_tracking  create_experiment/record_run/record_parameter/record_result → expt_*.jsonl
   ├─▶ classify_outcome  =  SUCCESS | FAILURE | PARTIAL | INCOMPLETE
   ├─▶ FAILURE → auto_classify_failure (9-category) → record_failure + record_lesson    → rmi_failures/lessons.jsonl
   ├─▶ SUCCESS → record_success (+ lesson)                                               → rmi_successes/lessons.jsonl
   └─▶ ingestion audit (dedup + hash chain)                                             → ring_ingestions.jsonl
                                                     │
   research_assistant.recall / failure_intelligence / mistake_check / perspectives  ◀───┘  now non-empty
```

The human approval gate (P53 research_loop) is unchanged and still required before any
strategy leaves research. This adapter only fills memory.

## 5. Historical backfill CLI

```
python -m jarvis.research_ingestion ingest-backtest --file raw_backtest.json \
       [--context ctx.json] [--commit]
```

- Loads a raw `backtest_runner` output JSON, maps it via `adapt()`, prints the
  `mapped_schema`, runs schema **validation**, checks for **duplicates** (idempotent),
  and writes the ingestion **audit** record.
- Without `--commit` it is a dry-run preview. `ingest_backtests()` handles batch backfill
  of many past results in one call.

## 6. Safety (Constitution-enforced, test-verified)

- No new storage; reuses P53 → `expt_*` / `rmi_*` ledgers; `ring_ingestions.jsonl` is the
  only P54-touched ledger (audit only), append-only + SHA256 hash chain.
- No execution path duplicated; adapter reads a *finished* result dict.
- No forbidden imports (`broker`/`execution`/`live_trading`/…), no forbidden defs
  (`execute`/`trade`/`deploy`/`allocate`/`approve`/`place_order`) — AST-scanned.
- Results are advisory (`is_advisory=True`, `is_decision=False`); human decision mandatory.
- Idempotent: same backtest re-ingested → no duplicate row anywhere.

## 7. Tests (`jarvis/research_ingestion/tests/test_backtest_adapter.py`, 21)

- fake backtest → **ledger updated**
- failed backtest → **failure intelligence** auto-created
- successful backtest → **success memory** auto-created
- ingest twice → **no duplicate**
- **recall finds it** (agent-shape result → `recall().tried_before`)
- missing validations → **INCOMPLETE** (not hidden); pure-mapping has no side effects;
  dry-run writes nothing; nested agent-shape & flat runner-shape both map; batch backfill;
  CLI `ingest-backtest`; forbidden-import / dangerous-def / model-id-leak scans.

## 8. Files

| File | Change |
|---|---|
| `jarvis/research_ingestion/backtest_adapter.py` | **new** — `adapt`, `ingest_backtest`, `ingest_backtests` |
| `jarvis/research_ingestion/__main__.py` | + `ingest-backtest` subcommand |
| `jarvis/research_ingestion/__init__.py` | export adapter functions |
| `jarvis/research_ingestion/tests/test_backtest_adapter.py` | **new** — 21 tests |
| `docs/backtest_ingestion_adapter.md` | this document |

Runners (`backtest_runner/*`, `jarvis/agents/backtest.py`) and all P1–P53 code: **unchanged**.
