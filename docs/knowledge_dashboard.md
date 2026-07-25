# Research Knowledge Dashboard (P138)

> Integration only — extends the Research OS console with a Research Brain Workspace. Read-only.

## What it does
New page `/research-os/brain` (Research OS nav → *Research Brain*) over `/console/research-brain`. Sections:

1. **Knowledge Graph** — the upgraded research-chain graph (Question→Hypothesis→Experiment→Result→Lesson)
2. **Past Research** — experiment/question nodes
3. **Failure Patterns** — `failure_intelligence` by category
4. **Strategy Memory** — strategy nodes
5. **Company Memory** — sector/macro-event nodes
6. **Conflicts** — contradicting conclusions (P135)
7. **Lessons** — lesson nodes; plus a Knowledge Health score (P139)

## Reuse & no-duplication
knowledge_graph_upgrade (P132), memory_audit (P131), conflict_detection (P135), knowledge_quality (P139),
failure_intelligence; existing console primitives. No new store.

## Governance
`is_advisory=True`, `is_decision=False`. Knowledge system only; no trading/execution.

## Files
`app/(console)/research-os/brain/page.tsx`, `lib/console-api.ts` (`getResearchBrain`),
`components/console/CommandRail.tsx`, `console_api.py`, this doc.
