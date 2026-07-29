# Experiment Planner (P74)

> Orchestration over expansion — inside `research_workflow`. Deterministic and **reproducible**
> (same hypothesis → same `spec_hash`). Reuses the existing validation checklist. Advisory.

## What it does — `experiment_planner.py`

`plan(hypothesis) → ExperimentSpec` deterministically defines every field the mission requires:

- **universe · timeframe · rebalance · feature_set · labels** — from a keyword profile
  (trend / mean-reversion / factor / supply-chain / default).
- **transaction_costs** — cost/slippage/spread bps (matching `research/validation` defaults).
- **walk_forward** — n_windows, min OOS fraction, consistency threshold.
- **random_baseline** — method, n_runs, seed (reproducible).
- **validation_checklist** — **reuses `research_ingestion.REQUIRED_VALIDATIONS`** (the 9 required
  validations), each PENDING until the backtest fills them.

`to_ingestion_schema()` emits a P53 backtest-schema skeleton (metrics empty → INCOMPLETE until
run), so the plan plugs straight into the existing backtest/validation/ingestion pipeline.

## Reproducibility

`spec_hash = content_digest(core spec)` — identical hypothesis yields an identical spec and hash,
verified by test. No randomness.

## Reuse analysis

Reuses `research_ingestion` (REQUIRED_VALIDATIONS + schema shape). No new engine, no new ledger,
no new validation logic — it *configures* the existing infrastructure.

## Validation

`tests/test_hypothesis_and_plan.py`: all fields defined, checklist == REQUIRED_VALIDATIONS,
reproducible hash, momentum profile, ingestion-schema skeleton, advisory.

## Remaining gaps

- Keyword profiles cover common families; unusual strategies fall back to a generic default.
- Period (start/end) is left blank for the human/backtester to set.

## Files

`research_workflow/experiment_planner.py`, tests, this doc.
