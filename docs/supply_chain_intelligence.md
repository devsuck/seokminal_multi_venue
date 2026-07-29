# Supply Chain Intelligence Expansion (P99)

> Integration only — turns the **existing** supply chain graph into an **Impact Propagation Engine**.
> **Reuses the existing graph infrastructure — does NOT create another graph database.** Read-only, deterministic.

## What it does — `jarvis/research_workflow/supply_chain_impact.py`
`propagate(event, *, max_depth=4, assistant)` → **Supply Chain Impact Report**
`{origin, affected_entities, direct_suppliers, customers, competitors, related_sectors,
relationship_graph, historical_events, uncertainty_note}`.

For each event it finds direct suppliers/customers/competitors/related sectors by walking the
existing `MarketEventIntelligence` relationship graph. Each affected entity carries
`{entity, category, distance, relationship_path, uncertainty}`; uncertainty rises with distance
(`d≤1 LOW`, `d==2 MEDIUM`, `d≥3 HIGH`). Example propagation:
`TSMC production issue → Apple → NVIDIA → AI_Server → Power_Infra`.

Relationship kinds are mapped to categories (`fab_supplier→supplier`, `component_of→customer`,
`competitor_of→competitor`, `etf_member→sector`, …). The reference graph is extended with a few
**static** edges (AI_Server, Power_Infra, SMH) — static reference data, **not** a store.

## Reuse & no-duplication
Reuses the `MarketEventIntelligence` relationship graph (P60) + `recall` for historical events.
**No new graph DB** — the engine is instantiated from `DEFAULT_RELATIONSHIPS` plus static extensions.

## Governance
`is_advisory=True`, `is_decision=False`. Uncertainty is surfaced, not hidden — human review required.

## Validation
`test_integration_p96_100.py`: TSMC propagation (≥3 affected, customer category), extended-graph nodes
(AI_Server/Power_Infra), unknown-origin empty result, AST safety.

## Files
`jarvis/research_workflow/supply_chain_impact.py`, `console_api.py`
(`/console/supply-chain-impact`, `/console/market-intel-feed` impact map), this doc.
