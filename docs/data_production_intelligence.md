# Data Production Intelligence (P151)

> Integration only — turns existing provider integrations into production-grade monitoring. **No data mutation.** Read-only.

## What it does — `jarvis/research_workflow/data_production.py`
`build_data_production()` → **DataProductionReport** per provider
`{provider, source, availability, freshness, quality_score, failure_reason, lineage}`.

Monitors API health, data freshness, schema consistency, missing data, and source reliability by reusing
`providers.provider_registry` (P112) and `data_quality.build_data_health` (P118). Quality score is
deterministic (availability minus data issues); lineage records the module/consumer/env-key. Nothing is
fetched or mutated.

## Reuse & no-duplication
providers (P112) + data_quality (P118) + P113–116 pipelines. No new store; no data mutation.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p151_160.py`: all report fields, no mutation, overall status.

## Files
`jarvis/research_workflow/data_production.py`, `console_api.py` (`/console/data-production`), this doc.
