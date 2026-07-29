# Research Validation Dashboard (P108)

> Integration only — extends the existing Research OS console. Read-only.

## What it does
New page `/research-os/validation` (Research OS nav → *Validation Loop*) over the unified
`/console/validation-loop` endpoint. Extends the existing console design system; no redesign.

## Sections
1. **Strategy Lifecycle Board** — every strategy's research state
   (`DISCOVERED → HYPOTHESIS → EXPERIMENT → BACKTEST → PAPER → REVIEW → ARCHIVED`), derived from existing
   ledgers (P105). Each row shows a stepper of completed states.
2. **Validation Panel** — backtest vs paper vs difference: tracked metrics (return/vol/drawdown/turnover/
   exposure/benchmark), divergence status, and the five-dimension gap with possible causes (P103 + P104).
3. **Quality Panel** — quality score, grade, the six core dimensions, weaknesses, missing evidence, and the
   accept / needs-more-evidence gate (P106).
4. **Review Queue** — operational events requiring human action (P107).
5. **Loop status** — v2.0 loop completeness + safety (P110).

The validation and quality panels run on a labelled demo (backtest success / paper failure) until live data
sources are connected; the lifecycle board, ops events, and audit are real projections of the ledgers.

## Backend surface
`/console/validation-loop`, `/console/strategy-lifecycle`, `/console/research-ops-events`,
`/console/research-trigger`, `/console/research-audit`, `/console/v2-release`. All read-only, `_safe`-wrapped.

## Governance
Every payload `is_advisory=True`, `is_decision=False`. No automatic trading/execution/allocation.

## Files
`app/(console)/research-os/validation/page.tsx`, `lib/console-api.ts` (`getValidationLoop`),
`components/console/CommandRail.tsx`, `api_server/console_api.py`, this doc.
