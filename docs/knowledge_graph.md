# Research Knowledge Graph Upgrade (P132)

> Integration only — extends the existing knowledge graph with the research chain. **No new graph database.**

## Research chain added
`Research Question → Hypothesis → Experiment → Result → Failure/Success → Lesson`

## What it does — `jarvis/research_workflow/knowledge_graph_upgrade.py`
`build_research_knowledge_graph(topic)` takes the existing `build_knowledge_graph` (P79) as the base
(Strategy/Experiment/Failure/Lesson/Sector nodes) and augments it with a Question/Hypothesis/Lesson layer
derived from `rwf_loops` (IDEA/HYPOTHESIS/EXPERIMENT stages) and `rmi_lessons`. New chain relationship kinds:
`asks, tests, yields, learned, similar_research, related_failure, related_company, related_strategy`.

Supports: similar research, related failures, related companies, related strategies — all as edges over the
existing graph. No new graph engine; the module merges nodes/edges on top of the reused base.

## Reuse & no-duplication
`build_knowledge_graph` (P79) + rwf_loops + rmi_lessons. No new graph DB.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p131_140.py`: research chain, chain kinds, base graph reused, determinism.

## Files
`jarvis/research_workflow/knowledge_graph_upgrade.py`, `console_api.py` (`/console/knowledge-graph`), this doc.
