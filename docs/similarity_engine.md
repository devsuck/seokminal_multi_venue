# Research Similarity Engine (P134)

> Integration only — compares research questions/strategies/experiments/companies. **No black-box embeddings.**

## What it does — `jarvis/research_workflow/research_similarity.py`
`ResearchSimilarity.compare(a, b, kind)` → a deterministic **similarity score** from token Jaccard on the
text plus feature overlap (feature_set/universe/timeframe). `rank(query, candidates)` orders candidates;
`similar_strategies(name)` delegates to the existing `strategy_lab.find_similar` (risk-profile/DNA based).

Uses existing metadata, features, and relationships — no embeddings, fully deterministic and explainable
(shared tokens are returned).

## Reuse & no-duplication
Deterministic set similarity + `strategy_lab.find_similar`. No model/store.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p131_140.py`: deterministic score, ranking order, feature similarity.

## Files
`jarvis/research_workflow/research_similarity.py`, this doc.
