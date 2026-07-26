# Research Conviction Framework (P163)

> Integration only — measures confidence in research. **Never an investment rating.** Read-only, deterministic.

## What it does — `jarvis/research_workflow/conviction_framework.py`
`build_conviction(topic)` → **ResearchConvictionReport** scoring six factors:

`Evidence Quality · Historical Similarity · Knowledge Consistency · Risk Level · Uncertainty · Validation Quality`

→ a conviction level `LOW / MEDIUM / HIGH`. Reuses `intelligence_quality` (P158), `semantic_recall` (P133),
`quality_monitor` (P106), and `conflict_detection` (P135). `is_investment_rating: False` — this is research
conviction, never a buy/sell rating.

## Reuse & no-duplication
intelligence_quality + recall + quality_monitor + conflict_detection. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `is_investment_rating=False`.

## Validation
`test_integration_p161_170.py`: six factors, valid level, not an investment rating.

## Files
`jarvis/research_workflow/conviction_framework.py`, `console_api.py` (`/console/conviction`), this doc.
