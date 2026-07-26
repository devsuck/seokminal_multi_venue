# Operational Metrics (P167)

> Integration only — measures operational efficiency. Read-only, deterministic.

## What it does — `jarvis/research_workflow/operational_metrics.py`
`build_operational_metrics()` → **OperationalMetricsReport** measuring:

`research throughput · research latency · agent utilization · API availability · data freshness ·
research completion · review backlog`

Derived deterministically from the existing append-only ledgers (rwf_/ring_/expt_), `data_production` (P151),
and `ops_events` (P107). Purpose: improve operational efficiency (human judgement).

## Reuse & no-duplication
Existing ledger reads + data_production + ops_events. No new store.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p161_170.py`: all seven metrics present.

## Files
`jarvis/research_workflow/operational_metrics.py`, `console_api.py` (`/console/operational-metrics`), this doc.
