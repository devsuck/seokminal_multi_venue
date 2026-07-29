# Backtest Research Bridge (P102)

> Integration only — connects the Experiment Planner to the **existing** backtest workflow.
> **The backtest engine is unchanged. No automatic execution.** Read-only, deterministic.

## What it does — `jarvis/research_workflow/backtest_bridge.py`
`create_job(hypothesis_or_spec)` → **BacktestResearchJob**
`{experiment_id, strategy, universe, parameters, validation_requirements, status}`.
A hypothesis is turned into an `ExperimentSpec` (P74 planner) first; validation requirements come from
the spec's checklist.

Status is a **research request** state, never a trading state:

`CREATED → WAITING_HUMAN → EXTERNAL_RUNNING → COMPLETED | FAILED`

- `submit_for_human_run(job)` → `WAITING_HUMAN` — a human runs the external backtest; Jarvis never runs it.
- `mark_running(job)` → `EXTERNAL_RUNNING`.
- `complete_job(job, backtest_result, commit=False)` consumes the result via the existing
  `research_ingestion.backtest_adapter.ingest_backtest` (idempotent, `commit=False` = dry-run preview),
  then sets `COMPLETED` or `FAILED` from the ingestion outcome.

The backtest is an **external stage** (`models.EXTERNAL_STAGES`) — this bridge only tracks the request
and consumes results.

## Reuse & no-duplication
`ExperimentPlanner.plan` (P74) + `backtest_adapter` (existing). No new backtest engine, no auto-execution,
no new ledger.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p101_110.py`: full status transitions, no auto-execution, ingestion consumed on complete.

## Files
`jarvis/research_workflow/backtest_bridge.py`, `console_api.py`, this doc.
