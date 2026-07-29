# Hypothesis Generator (P73)

> Orchestration over expansion — inside `research_workflow`, composing existing engines.
> Deterministic. Stored through the existing memory infrastructure. Advisory; the human decides.

## What it does — `hypothesis_generator.py`

Generates candidate hypotheses from the existing subsystems and returns fully-structured objects:

| Source | Reused engine |
|---|---|
| historical failures, memory graph, unexplored factor interactions | `ResearchQueueEngine` (P58 — COMBINATION / FAILURE_FIX / REGIME / EVENT) |
| supply-chain relationships | `MarketEventIntelligence` relationship graph (P60) |
| portfolio context | supplied portfolio → diversification hypothesis |
| macro regime | passed through to the queue |

Every `Hypothesis` includes the mission-required fields: **rationale**, **expected edge**
(LOW/MEDIUM/HIGH), **assumptions**, and **invalidation conditions** — filled from deterministic
per-source templates.

## Storage through existing memory

`store(hypothesis, commit=True)` writes an `rmi_` **lesson** (the shared memory backbone), so the
hypothesis is later found by `recall()` — no new store. Persisted-and-recalled is test-verified.

## Reuse analysis

Composes P58 queue + P60 events + `rmi_`; adds only the structured-hypothesis shaping and
source-specific assumption/invalidation templates. No new engine, no new ledger.

## Validation

`tests/test_hypothesis_and_plan.py`: required fields present, supply-chain + portfolio hypotheses
included (reserved slots), determinism, **persisted → recalled**, dry-run no-write, safety scans.

## Remaining gaps

- Expected edge is qualitative (source-derived), not yet quantified against historical hit rates.
- Factor-interaction hypotheses come via the queue's token combinations; explicit factor-pair
  enumeration could broaden coverage.

## Files

`research_workflow/hypothesis_generator.py`, tests, this doc. Surfaced via
`/console/autonomous-runtime` preview.
