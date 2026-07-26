# Intelligence Quality Scoring (P158)

> Integration only — measures information reliability. Read-only, deterministic.

## What it does — `jarvis/research_workflow/intelligence_quality.py`
`score_intelligence(topic, n_sources)` → **IntelligenceQualityReport** scoring five dimensions:

`Data quality · Evidence quality · Historical relevance · Conflict level · Uncertainty`

and a combined **confidence** — HIGH (multiple sources + historical support), LOW (single source +
conflicting evidence), else MEDIUM. Reuses `data_production` (P151, data quality + source count),
`semantic_recall` (evidence + history), and `conflict_detection` (P135, conflict level).

## Reuse & no-duplication
data_production + semantic_recall + conflict_detection + knowledge_quality. No new store.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p151_160.py`: five dimensions, valid confidence, single-source→LOW.

## Files
`jarvis/research_workflow/intelligence_quality.py`, `console_api.py` (`/console/intelligence-quality`), this doc.
