# Strategy Lifecycle Management (P105)

> Integration only — tracks research state. **Research state only — NOT a trading state.** Read-only.

## What it does — `jarvis/research_workflow/strategy_lifecycle.py`
Lifecycle:

`DISCOVERED → HYPOTHESIS → EXPERIMENT → BACKTEST → PAPER → REVIEW → ARCHIVED`

`lifecycle_state(strategy)` derives the current state (the furthest stage reached) plus per-stage evidence,
deterministically, from the existing append-only ledgers — by reusing `timeline.build_timeline`, which
already reconstructs research history from `rwf_/ring_/expt_/rmi_/ras_`. Timeline stages map to lifecycle
states (Idea→DISCOVERED, Backtest→BACKTEST, Paper/Validation→PAPER, Decision/Human Review→REVIEW, …).

`board(strategies=None)` renders every strategy's current state; when no list is given, strategy names are
derived from the ingestion/memory ledgers.

## Reuse & no-duplication
`timeline.build_timeline` (P78) over existing ledgers. No new state store — state is a projection, not a
record. This is a research-progress state, never a capital-deployed trading state.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p101_110.py`: lifecycle order, state derivation, board rows.

## Files
`jarvis/research_workflow/strategy_lifecycle.py`, `console_api.py` (`/console/strategy-lifecycle`), this doc.
