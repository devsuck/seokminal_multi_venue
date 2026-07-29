# Research Data Pipeline (P53)

> Governed by `docs/CONSTITUTION.md` and `docs/AGENTIC_RESEARCH_EVOLUTION.md`.
> **Integration over expansion** — this pipeline creates NO new experiment/failure storage.
> It orchestrates existing engines so completed backtests become research memory.

## Problem it fixes

The memory infrastructure exists but was empty: `recall()`, `failure_intelligence()`,
`perspectives()` returned 0 because nothing wrote to the ledgers they read
(`expt_*.jsonl`, `rmi_failures/lessons/successes.jsonl`).

## Current flow (before)

```
backtest_runner ──▶ (nothing) ──▶ empty ledgers ──▶ recall()=∅
```

## Future flow (this pipeline)

```
Backtest result (dict)
   │  research_ingestion.ingest()
   ├─▶ experiment_tracking.create_experiment / record_run / record_parameter / record_result   → expt_*.jsonl
   ├─▶ classify_outcome() = SUCCESS | FAILURE | PARTIAL | INCOMPLETE
   ├─▶ if FAILURE: auto_classify_failure() (9-category taxonomy)
   │        research_memory_intelligence.record_failure + record_lesson                          → rmi_failures/lessons.jsonl
   ├─▶ if SUCCESS: record_success (+ record_lesson)                                              → rmi_successes/lessons.jsonl
   └─▶ research_ingestion audit record (dedup + hash)                                            → ring_ingestions.jsonl
                                   │
                                   ▼
         research_assistant.recall / failure_intelligence / perspectives  ← now populated
```

## Data schemas

### Backtest input (dict — the ingestion interface)
| field | notes |
|---|---|
| `strategy_name` (required) | experiment identity |
| `strategy_version` | code_version on the run |
| `hypothesis` | run note / experiment objective |
| `universe`, `period` (`start`/`end`) | parameters (research context) |
| `features` (list), `entry_rules`, `exit_rules`, `risk_rules` | parameters |
| `metrics` (dict) | `return · sharpe · max_drawdown · volatility · walk_forward · out_of_sample · cost_impact · parameter_stability · random_baseline` |
| `outcome` (optional) | explicit SUCCESS/FAILURE/PARTIAL; else derived |
| `root_cause` / `failure_reason` (optional) | classified into taxonomy; else derived from metrics |
| `lesson` (optional) | else default per failure category |
| `source`, `timestamp` | provenance |

### Experiment record (existing `expt_*` schema) — unchanged
experiment (name/objective/tags) → run (code_version/note) → parameters (context) → results (numeric metrics).

### Failure/lesson record (existing `rmi_*` schema) — unchanged
`record_failure(origin=experiment_id, summary, evidence={category, root_cause, lesson, metrics})`,
`record_lesson(origin, lesson, impact)`.

### Ingestion audit (`ring_ingestions.jsonl`) — new, thin
`ingestion_id` (deterministic: strategy_name + backtest_hash) · `backtest_hash` · `experiment_id` ·
`run_id` · `outcome` · `failure_category` · `validation_complete` · hash chain. Enables dedup +
hash verification without duplicating experiment storage.

## Outcome & failure classification (deterministic)

- `classify_outcome(metrics)`: SUCCESS if sharpe≥0.5 and (oos≥0.3 or absent) and max_drawdown≥-0.35;
  PARTIAL if 0≤sharpe<0.5; INCOMPLETE if required validations missing; FAILURE otherwise.
- `auto_classify_failure(metrics, reason)`: uses `research_assistant.classify_failure(reason)` when a
  reason is given; else metric heuristics — in-sample vs OOS gap → OVERFITTING, high cost_impact →
  COST_SENSITIVITY, low parameter_stability → PARAMETER_INSTABILITY, unbeaten random baseline →
  POOR_HYPOTHESIS, regime flag → REGIME_CHANGE, else UNCLASSIFIED.

## Validation standardization

`REQUIRED_VALIDATIONS` = return · sharpe · max_drawdown · volatility · walk_forward · out_of_sample ·
cost_impact · parameter_stability · random_baseline. Missing any → experiment marked **INCOMPLETE**
(recorded, not auto-rejected).

## Audit / safety (unchanged principles)

Append-only · immutable · hash-chained · idempotent (deterministic IDs → re-ingest is a no-op) ·
human decision authority · **no execution / broker / live trading / capital allocation**. The pipeline
only *records* completed backtests; it never runs or deploys anything.

## Remaining gaps / next

- Real `backtest_runner` output is in the trading layer; a small adapter maps its result dict to this
  schema (thin, per-project). Historical backfill uses the same `ingest()` interface (schema-validated,
  deduped, hash-verified) — no fabricated data.
