# Research Workflow

This guide walks through an end-to-end research plan using `jarvis.research_manager`,
the event-sourced plan lifecycle at the core of the Autonomous Quant Research OS.
Everything here is research/analysis/recording only: no orders, no deployment,
no capital allocation. State is persisted to an append-only, SHA256 hash-chained
JSONL ledger located at `jarvis.config.state_path`.

## Lifecycle

A plan moves deterministically through:

```text
CREATED -> PLANNED -> RUNNING -> COMPLETED -> REVIEWED -> ARCHIVED
```

Progress events drive the transitions. IDs are deterministic, so a `replay`
reproduces identical state.

## 1. Create a plan

Omit `--commit` for a dry-run; add it to persist to the ledger.

```bash
# dry-run first
python -m jarvis.research_manager plan "Vol-carry factor study"

# persist
python -m jarvis.research_manager plan "Vol-carry factor study" --commit
```

## 2. Add tasks and dependencies

```bash
python -m jarvis.research_manager task PLAN-1 "Ingest OHLCV panel" --commit
python -m jarvis.research_manager task PLAN-1 "Compute carry signal" --commit
python -m jarvis.research_manager task PLAN-1 "Backtest signal" --commit

# make the backtest depend on the signal task
python -m jarvis.research_manager depend TASK-3 --on TASK-2 --commit
```

Dependencies form a DAG; a task cannot progress until its parents complete.

## 3. Track progress

Progress events move the plan from `PLANNED` into `RUNNING` and eventually
`COMPLETED`.

```bash
python -m jarvis.research_manager progress TASK-1 --status done --commit
python -m jarvis.research_manager progress TASK-2 --status done --commit
python -m jarvis.research_manager progress TASK-3 --status done --commit
python -m jarvis.research_manager complete PLAN-1 --commit
```

## 4. Non-binding status report

Reports are advisory records (`is_binding=False`). A `VALIDATED` verdict
is a recorded opinion, never a deployment.

```bash
python -m jarvis.research_manager report PLAN-1 --commit
python -m jarvis.research_manager review PLAN-1 --commit
python -m jarvis.research_manager archive PLAN-1 --commit
```

## 5. Verify and replay

```bash
python -m jarvis.research_manager verify        # checks hash-chain integrity
python -m jarvis.research_manager replay PLAN-1  # rebuilds identical state
python -m jarvis.research_manager summary
```

Because the ledger is append-only and deterministic, `verify` detects any
tampering and `replay` always yields the same result.
