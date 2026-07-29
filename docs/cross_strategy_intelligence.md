# Cross Strategy Intelligence (P83)

> Compares strategies automatically by reusing Portfolio Intelligence, the risk reasoner, and
> recall. Deterministic, read-only, no new engine.

## What it does — `jarvis/research_workflow/cross_strategy.py` + `/console/cross-strategy`
`compare(a, b)` computes, deterministically:
- **similarity** (strategy-type match + shared-lesson Jaccard + |correlation|),
- **correlation** & **portfolio overlap** — reuses `PortfolioIntelligence.combination_analysis`,
- **conflict** (strongly negative correlation),
- **shared lessons** — intersection of `recall` refs,
- **shared risks** — intersection of `StrategyRiskReasoner` category flags,
- **decision differences** — each strategy's main risk.

`compare_all(strategies)` builds the pairwise matrix. The endpoint derives strategies (and their
metrics) from the experiment ledger and compares the top ones.

## Reuse & no-duplication
No new portfolio/risk engine — it composes P61 + P62 + recall. Read-only.

## Validation
`test_integration_p78_85.py`: compare (corr −1 → conflict), determinism, full matrix count.
Endpoint shape test.

## Files
`jarvis/research_workflow/cross_strategy.py`, `console_api.py`, this doc.
