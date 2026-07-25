# Research Knowledge Graph (P79)

> Reuses existing graph infrastructure (`research_assistant.memory_graph` +
> `event_intelligence.relationship_graph`) and combines it with ledger-derived nodes. Read-only.

## What it does — `jarvis/research_workflow/knowledge_graph.py` + `/console/research-graph`
Builds one multi-entity graph connecting **Experiment · Strategy · Failure · Lesson · Portfolio ·
MacroEvent · Sector · Risk · DecisionMemo · PaperResult**, with the relationship kinds
**uses · affects · failed · supports · contradicts · validated_by · similar_to · tested_after ·
caused_by**, by composing:
- `memory_graph()` → Experiment→Failure→Lesson (reused as-is),
- `relationship_graph()` → supply-chain/sector `affects` edges (reused),
- `ring_ingestions` → Strategy `uses` Experiment, `failed`/`validated_by`, `tested_after`,
- risk-profile match → `similar_to` between strategies,
- `ras_notes` → DecisionMemo `supports`.

## Reuse & no-duplication
No new graph engine — it merges two existing graph builders plus ledger reads. The page
(`/research-os/graph`) renders a columnar SVG with click-to-highlight; no charting library.

## Validation
`test_integration_p78_85.py`: multi-entity nodes, relationship kinds present, determinism.
Endpoint shape test. Live screenshot (26 nodes / 24 edges from seed).

## Files
`jarvis/research_workflow/knowledge_graph.py`, `console_api.py`,
`app/(console)/research-os/graph/page.tsx`, `lib/console-api.ts`, this doc.
