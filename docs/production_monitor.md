# Production Monitoring (P166)

> Integration only — monitors production components. Read-only.

## What it does — `jarvis/research_workflow/production_monitor.py`
`build_production_status()` → **ProductionStatusReport** across seven components with severity
`OK / WARNING / CRITICAL`:

`API health · Agent health · Research pipeline · Scheduler · Dashboard · Memory health · Knowledge health`

Reuses `data_production` (P151, API), `agent_validation` (P130), `health_monitor` (P77, pipeline),
`research_scheduler` (P141), `continuous_learning.learning_status` (memory), and `knowledge_quality` (P139).

## Reuse & no-duplication
Existing monitors across all layers. No new store.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p161_170.py`: seven components, valid severities.

## Files
`jarvis/research_workflow/production_monitor.py`, `console_api.py` (`/console/production-status`), this doc.
