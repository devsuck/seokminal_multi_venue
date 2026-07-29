# Portfolio Research View (P164)

> Integration only — a research perspective only. **No allocation suggestions.** Read-only.

## What it does — `jarvis/research_workflow/portfolio_research_view.py`
`build_portfolio_research(strategies, correlations, market)` displays, from a research angle:
`sector exposure · factor exposure · strategy overlap · correlation · concentration · scenario comparison`.

Reuses `strategy_health` (P144), `cross_asset_intelligence` (P156), and the risk-profile lens. Strategy
overlap and factor exposure come from strategy-type profiles; scenario comparison is a research focus, not an
allocation. **No allocation suggestions are produced.**

## Reuse & no-duplication
strategy_health + cross_asset_intelligence + risk. No new store, no allocation.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p161_170.py`: all six views, no allocation.

## Files
`jarvis/research_workflow/portfolio_research_view.py`, `console_api.py` (`/console/portfolio-research`), this doc.
