# Institutional Intelligence Validation (P160)

> Validation of the institutional intelligence layer. Read-only, deterministic, no execution.
> (Module: `institutional_intelligence_validation.py`.)

## What it verifies — `jarvis/research_workflow/institutional_intelligence_validation.py`
`validate_intelligence()` runs seven checks:
1. **data_sources_connect** — data production reports providers
2. **sector_context_generated** — sector intelligence produces entities + questions
3. **macro_context_generated** — macro context produces a state + indicators
4. **company_graph_works** — company intelligence produces relationships (not a signal)
5. **research_context_combines** — the 8-section research context package assembles
6. **quality_scoring_works** — intelligence quality yields a confidence + 5 dimensions
7. **no_duplicate_systems** — ledger stays 3; modules never write ledgers directly (AST)

`intelligence_safety()` AST-scans all P151–160 modules: no new database/ledger/vector-db/memory-store/
execution-engine, no `execute/trade/place_order/allocate/approve`, no broker/capital deployment.

## Result
All seven checks pass; safety clean; ledger stays 3.

## Validation
`test_integration_p151_160.py`: seven checks, safety no-new-ledger.

## Files
`jarvis/research_workflow/institutional_intelligence_validation.py`, `console_api.py`
(`/console/intelligence-validation`), this doc.
