# Research Operations Event System (P107)

> Integration only — connects the existing event layer into operational events.
> **No new notification database.** Read-only, deterministic.

## What it does — `jarvis/research_workflow/ops_events.py`
`ops_events()` derives operational events from the existing append-only ledgers and classifies them into
five types:

- `NEW_HYPOTHESIS` — from `rwf_loops` (HYPOTHESIS / UPDATED_HYPOTHESIS)
- `BACKTEST_COMPLETED` — from `ring_ingestions`
- `VALIDATION_FAILED` — from `ring_ingestions` (FAILURE) and `rmi_failures`
- `PAPER_DIVERGENCE` — from `rmi_lessons` carrying the `PAPER vs BACKTEST` marker
- `HUMAN_REVIEW_REQUIRED` — from `rwf_runs` (HUMAN_DECISION / DECISION)

Events are sorted newest-first and a `review_queue` (events needing human action) is surfaced.

## Reuse & no-duplication
Reads the existing event layer (`rwf_`, `ring_`, `rmi_` ledgers). **No new notification store** — events are
a projection of what is already recorded.

## Governance
`is_advisory=True`, `is_decision=False`; review-queue items carry `requires_human_review=True`.

## Validation
`test_integration_p101_110.py`: exactly the five event types, read-only projection.

## Files
`jarvis/research_workflow/ops_events.py`, `console_api.py` (`/console/research-ops-events`), this doc.
