# Data Quality Operations (P118)

> Integration only — monitors data-source health. **Read-only, no new store.** Integrated into the Executive Cockpit.

## What it does — `jarvis/research_workflow/data_quality.py`
`build_data_health(series_by_source, rows_by_source, now)` produces a **DataHealthReport** with five checks:

`API availability · data freshness · schema changes · missing values · abnormal values`

- **API availability** from `providers.provider_registry()` (env-var presence, no network).
- **freshness / missing / abnormal** reuse the existing `market_data.quality.assess_series` (staleness,
  missing bars, abnormal jumps).
- **schema changes / missing fields** checked against the minimal normalization schema.

Overall status is `HEALTHY / DEGRADED / LIMITED`. The report is folded into `cockpit.build_cockpit()` under
`data_health`, so it appears in the Executive Cockpit.

## Reuse & no-duplication
`market_data.quality.assess_series` (existing), `providers.provider_registry` (P112). No new store/ledger.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p111_120.py`: report shape + 5 checks, freshness uses existing quality, cockpit integration.

## Files
`jarvis/research_workflow/data_quality.py`, `jarvis/research_workflow/cockpit.py` (integration),
`console_api.py` (`/console/data-health`), this doc.
