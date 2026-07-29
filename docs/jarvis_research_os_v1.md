# Jarvis Investment Research OS v1.0 (P95)

> The final integrated operating screen. Integration & visualization only — reuses every prior
> capability. Read-only; the human makes every decision.

## What it does — `jarvis/research_workflow/market_cockpit.py` + `/console/market-cockpit`
`build_market_cockpit()` composes the full flow, in order:

```
Market State (P87 regime) → Research Opportunities (P88) → Active Experiments (P72 loop) →
Validation Status (P81 health) → Risk (P62) → Portfolio Context (P61/paper) →
Decision Queue (P68 human review) → Knowledge Growth (P79/P82)
```

The dashboard page `/research-os/market` is the **primary operating screen**: regime panel
(labels + historical matches + recommended/avoid), opportunity queue, validation coverage meters,
risk, portfolio, and decision queue — auto-refreshing.

## Reuse & no-duplication
Every section reuses an existing module/endpoint. **No new engine, no new ledger, no new API
logic.** Governance unchanged (files inside `research_workflow`).

## The final vision, realized
Jarvis now functions as an AI-powered investment research organization: it observes markets,
discovers research opportunities, remembers previous failures, challenges ideas (7-perspective
council), evaluates evidence, explains uncertainty, and supports human investment decisions — but
never trades, never allocates capital, never replaces human judgment.

## Validation
`test_integration_p86_95.py`: market cockpit contains all 8 flow sections, determinism,
`is_decision=False`. Endpoint shape test.

## Files
`jarvis/research_workflow/market_cockpit.py`, `console_api.py` (market-cockpit),
`app/(console)/research-os/market/page.tsx`, `CommandRail.tsx`, this doc.
