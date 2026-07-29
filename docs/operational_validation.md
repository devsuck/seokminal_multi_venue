# Operational Validation (P120)

> Validation of the full external-data → memory chain. Read-only, deterministic, no execution.

## The chain
`External Data → Provider → Normalization → Event Intelligence → Research Trigger → Workflow → Validation Loop → Memory`

## What it verifies — `jarvis/research_workflow/operational_validation.py`
`validate_operations()` runs five deterministic checks on sample external data:
1. **data_ingestion_works** — market pipeline produces research events
2. **duplicate_events_prevented** — feed dedup drops repeated events
3. **research_candidates_generated** — feed produces an opportunity queue
4. **dashboard_displays_updates** — the live-intelligence surface assembles
5. **existing_ledgers_unchanged** — `research_workflow` ledger stays exactly 3

`architecture_safety()` AST-scans all P111–120 modules: no new database/ledger/memory/execution engine, no
`execute/trade/place_order/allocate/approve`, no broker/live-trading imports.

## Architecture safety — confirmed
- No new database, ledger, memory system, or execution engine
- Reuses event system, `research_workflow`, `rmi_`, and the existing dashboard
- Advisory only; human is the only decision maker

## Validation
`test_integration_p111_120.py`: all five checks pass, `operational=True`, safety clean, no new ledger.

## Files
`jarvis/research_workflow/operational_validation.py`, `console_api.py` (`/console/operational-validation`), this doc.
