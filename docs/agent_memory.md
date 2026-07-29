# Agent Memory Integration (P137)

> Integration only — connects the research agents to the knowledge layer. **No direct ledger writes.**

## What it does — `jarvis/research_workflow/agent_memory.py`
`knowledge_informed_research(objective)` wires the agents to memory across the research lifecycle:
- **Before** — the Director receives *previous knowledge* via `semantic_recall` (P133)
- **During** — the agents run the multi-agent workflow (P128) with that context
- **After** — the Writer stores a *final lesson* via `learning_engine` (P136) → existing `rmi_`

All persistence goes through existing engines (`record_lesson`, `session_manager`, `record_advisory`) —
`direct_ledger_writes: False`. `commit=False` = preview.

## Reuse & no-duplication
semantic_recall + multi_agent_workflow + learning_engine. No direct ledger writes, no new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p131_140.py`: before/during/after present, no direct ledger writes.

## Files
`jarvis/research_workflow/agent_memory.py`, `console_api.py` (`/console/research-brain`), this doc.
