# Research Context Engine (P155)

> Integration only — combines all intelligence into one research context. Read-only.

## What it does — `jarvis/research_workflow/research_context_engine.py`
`build_research_context(question, entity, sector, macro, market)` → **ResearchContextPackage** with eight
sections:

1. Question · 2. Current Environment (regime + macro) · 3. Historical Similar Cases · 4. Relevant Companies ·
5. Relevant Strategies · 6. Known Risks · 7. Contradictions · 8. Missing Evidence

Combines market state, macro state (P153), sector (P152), company (P154), historical memory
(`semantic_recall`, P133), and contradictions (`conflict_detection`, P135) over the knowledge graph (P132).

## Reuse & no-duplication
semantic_recall + knowledge_graph + conflict_detection + macro/sector/company intelligence. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p151_160.py`: exactly 8 sections including contradictions + missing evidence.

## Files
`jarvis/research_workflow/research_context_engine.py`, `console_api.py` (`/console/research-context`), this doc.
