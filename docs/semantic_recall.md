# Semantic Research Recall (P133)

> Integration only — when an agent receives a question, automatically retrieve relevant knowledge. Read-only.

## What it does — `jarvis/research_workflow/semantic_recall.py`
`recall_context(question)` → **Research Context Package**:
`{relevant_experiments, similar_failures, past_conclusions, contradicting_evidence, memory_refs}`.

Example — *"Does momentum work in current regime?"* returns previous momentum studies, failure reasons,
past conclusions, and any contradicting perspectives.

Reuses `recall` (topic hits across expt_/ring_/rmi_), `mistake_check` + `failure_intelligence` (similar
failures), `perspectives` (contradicting evidence when lenses conflict), and
`ResearchMemoryIntelligenceEngine.retrieve_context` (rmi_ scored retrieval). **No new vector database.**

## Reuse & no-duplication
recall / mistake_check / perspectives / failure_intelligence / retrieve_context. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p131_140.py`: all four package fields present.

## Files
`jarvis/research_workflow/semantic_recall.py`, `console_api.py` (`/console/semantic-recall`), this doc.
