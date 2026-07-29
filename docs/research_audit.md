# Research Audit & History (P109)

> Integration only — guarantees every strategy has a complete research lineage.
> **Reuses existing append-only ledgers. No new audit database.** Read-only, deterministic.

## What it does — `jarvis/research_workflow/research_audit.py`
`audit_strategy(strategy)` reconstructs the full lineage from the existing ledgers (reusing
`timeline.build_timeline`) into sections:

`origin_event · hypothesis · experiments · backtests · results · failures · lessons · decisions · archive`

Parameters are pulled from the `expt_` ledger. A completeness check flags any strategy missing a required
section (`origin_event, hypothesis, experiments, backtests, lessons`).

`audit_coverage()` summarises completeness across all known strategies and lists the incomplete ones.

## Reuse & no-duplication
`timeline.build_timeline` (P78) + `experiment_tracking` ledger reads. The truth already lives in the
append-only ledgers (`rwf_/ring_/expt_/rmi_/ras_`) — the audit is a projection, **not** a new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p101_110.py`: all sections reconstructed, completeness present, coverage summary.

## Files
`jarvis/research_workflow/research_audit.py`, `console_api.py` (`/console/research-audit`), this doc.
