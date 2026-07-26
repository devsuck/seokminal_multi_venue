# Sector Intelligence Engine (P152)

> Integration only — understands market sectors and themes. **No investment ranking.** Read-only.

## What it does — `jarvis/research_workflow/sector_intelligence.py`
`analyze_sector(sector)` → **SectorIntelligenceReport**
`{sector, key_entities, events, historical_context, risk_factors, research_questions}`.

Analyzes sector relationships (via `supply_chain_impact.propagate`), sector events (`event_stream`), company
concentration, and historical sector behavior (`recall`). Deterministic risk factors and research questions;
**no ranking of investments**.

## Reuse & no-duplication
knowledge_graph + company_monitor + supply_chain_impact + market intelligence. No new store.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p151_160.py`: all report fields, no investment ranking.

## Files
`jarvis/research_workflow/sector_intelligence.py`, `console_api.py` (`/console/sector-intelligence`), this doc.
