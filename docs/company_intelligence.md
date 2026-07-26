# Company Intelligence Graph (P154)

> Integration only — expands company understanding. **No buy/sell signals.** Read-only.

## What it does — `jarvis/research_workflow/company_intelligence.py`
`analyze_company(entity)` → **CompanyIntelligenceReport**
`{entity, relationships, events, financial_context, historical_lessons, risks}`.

Tracks a company's suppliers/customers/competitors/industries (via `supply_chain_impact.propagate`), events +
financial context (via `company_monitor`, P143), and historical lessons (via `semantic_recall`, P133).
Deterministic risks; **no buy/sell signal**.

## Reuse & no-duplication
knowledge_graph + company_monitor + fundamental_pipeline + supply_chain_impact. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `is_trade_signal=False`.

## Validation
`test_integration_p151_160.py`: all report fields, relationships, not a signal.

## Files
`jarvis/research_workflow/company_intelligence.py`, `console_api.py` (`/console/company-intelligence`), this doc.
