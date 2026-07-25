# Research Prioritizer (P76)

> Orchestration over expansion — inside `research_workflow`. Deterministic and **consistent**
> (same input → same ranking). Advisory; the human decides. Reuses `recall` for novelty/relevance.

## What it does — `research_prioritizer.py`

`prioritize(candidates) → RankedQueue` scores each candidate on **seven factors** and ranks them:

| Factor | Basis |
|---|---|
| novelty | `1 − min(1, recall_hits/5)` — fewer memory hits = more novel |
| expected_information_gain | `½·novelty + ½·edge` |
| implementation_cost | source-derived (failure-fix cheap, event/supply-chain costlier) |
| portfolio_impact | source-derived (portfolio/combination higher) |
| historical_relevance | `min(1, recall_hits/5)` |
| confidence | HIGH/MEDIUM/LOW → 0.9/0.6/0.3 |
| uncertainty | `1 − confidence` |

A deterministic weighted composite ranks the queue, with a stable tie-break on `hypothesis_id`.
`recommend_next(candidates)` returns the top item — what should be researched next.

## Consistency

Same candidates → identical order and identical recommendation (test-verified). No randomness;
`recall`-based factors are read-only.

## Reuse analysis

Reuses `research_assistant.recall` (novelty + historical relevance) and consumes P73 hypotheses /
P58 proposals as candidates. No new engine, no new ledger.

## Validation

`tests/test_critic_prioritizer_loop.py`: ranks with all 7 factors, **consistent ordering**,
recommend-next, advisory.

## Remaining gaps

- Weights are fixed and transparent, not learned from realized outcomes.
- Novelty uses topic-level recall; a finer semantic novelty measure could refine it.

## Files

`research_workflow/research_prioritizer.py`, tests, this doc. Drives the autonomous loop's
Hypothesis and Next-Experiment stages; surfaced via `/console/autonomous-runtime`.
