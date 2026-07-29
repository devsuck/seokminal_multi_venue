# Cross Asset Intelligence (P156)

> Integration only — connects different asset classes. **No portfolio allocation.** Read-only.

## What it does — `jarvis/research_workflow/cross_asset_intelligence.py`
`build_cross_asset(correlations, market)` → **CrossAssetReport** across
`Equity · ETF · Index · Commodity · FX · Macro`.

Analyzes correlation (labelled from injected values), relationship changes (high-correlation pairs flagged
for regime-transition de-diversification), historical regimes (`recall`), and a static risk-transmission map
(macro→equity, commodity→equity, FX↔commodity, …). Reuses `regime` and the supply-chain relationship graph.
**No portfolio allocation.**

## Reuse & no-duplication
supply_chain relationship graph + regime + recall. No new store, no allocation.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p151_160.py`: six asset classes, correlations, risk transmission, no allocation.

## Files
`jarvis/research_workflow/cross_asset_intelligence.py`, `console_api.py` (`/console/cross-asset`), this doc.
