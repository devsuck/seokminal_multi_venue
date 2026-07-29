# Strategy Laboratory (P91)

> Integration only — represents strategies as reusable **research objects** (Strategy DNA).
> Reuses experiment tracking, failure intelligence, knowledge graph, cross-strategy. Read-only.

## What it does — `jarvis/research_workflow/strategy_lab.py` + `/console/strategy-lab`
`strategy_dna(name, spec)` assembles a strategy's DNA from existing data:
**factors · universe · time horizon · entry logic · exit logic · risk model · validation method ·
failure history · successful regimes**. `find_similar` reuses P83 cross-strategy;
`repeated_mistakes` reuses `mistake_check`.

- Risk model + type come from `StrategyRiskReasoner`; failure history from `mistake_check`;
  successful regimes from the P87 regime→strategy mapping.

## Reuse & no-duplication
Reuses P62 risk, P56 failure intelligence, P83 cross-strategy; no new engine, no new store.

## Validation
`test_integration_p86_95.py`: DNA fields (type/factors/horizon/failure history), repeated mistakes.

## Files
`jarvis/research_workflow/strategy_lab.py`, `console_api.py`,
`app/(console)/research-os/strategy-lab/page.tsx`, this doc.
