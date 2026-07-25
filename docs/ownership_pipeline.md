# Insider & Ownership Intelligence (P116)

> Integration only — connects insider transactions / institutional ownership / fund flows.
> **Research trigger only — not a buy signal.** Read-only, deterministic.

## What it does — `jarvis/research_workflow/ownership_pipeline.py`
`run(transactions, *, source)` maps ownership records through `insider_flow.analyze_transaction` (P98) into
an **Ownership Event** `{company, actor, transaction, size, date, historical_context}` plus a research-trigger
queue.

## Reuse & no-duplication
`insider_flow.analyze_transaction` (P98) → `recall`. No new store/engine.

## Governance
`is_research_trigger=True`, `is_trade_signal=False`, `is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p111_120.py`: all Ownership Event fields, not a trade signal.

## Files
`jarvis/research_workflow/ownership_pipeline.py`, `console_api.py` (`/console/live-intelligence`), this doc.
