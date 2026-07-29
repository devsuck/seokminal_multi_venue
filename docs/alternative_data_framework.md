# Alternative Data Intelligence (P89)

> Integration only — an **architecture** for alt-data as research evidence (not signals). No
> external providers required. Connects Alt Data → Company/Sector → Knowledge Graph → Research Memory.

## What it does — `jarvis/research_workflow/alt_data.py` + `/console/alt-data`
`catalog()` exposes the supported sources and their entity mapping: **shipping, satellite,
web traffic, hiring, app rankings, social sentiment, search trends**. `observe(source, entity,
value)` maps an observation to a company/sector, recalls related research, and (on commit) stores
it as an `rmi_` **research-evidence lesson** — reusing existing memory, no new store.

Every observation is `is_research_evidence=True`, `is_trade_signal=False`.

## Reuse & no-duplication
Reuses the knowledge graph (entity connection) and `rmi_` memory. The framework is provider-
agnostic; wiring a real provider is a later step.

## Validation
`test_integration_p86_95.py`: catalog (7 sources), observe maps entity, unknown-source guard.

## Files
`jarvis/research_workflow/alt_data.py`, `console_api.py`, this doc.
