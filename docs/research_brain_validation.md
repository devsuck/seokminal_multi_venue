# Research Brain Validation (P140)

> Validation of the knowledge-brain chain. Read-only, deterministic, no execution.

## The chain
`New Research Question → Recall Previous Knowledge → Agent Analysis → Conflict Check → Research Result → Lesson Update`

## What it verifies — `jarvis/research_workflow/brain_validation.py`
`validate_brain()` runs five checks:
1. **past_research_retrieved** — semantic_recall produces a Research Context Package
2. **failures_reused** — the package carries similar failures + contradicting evidence
3. **no_duplicate_memory** — ledger stays 3; knowledge_quality reports issues
4. **agents_use_knowledge** — agent_memory runs before/during/after with no direct ledger writes
5. **dashboard_displays_knowledge** — the research-brain graph assembles

`brain_safety()` AST-scans all knowledge modules: no new database/ledger/memory-store/vector-db, knowledge
system only, no `execute/trade/approve/allocate`, no broker.

## Result
All five checks pass; safety clean; ledger stays 3.

## Validation
`test_integration_p131_140.py`: five checks, safety no-new-ledger.

## Files
`jarvis/research_workflow/brain_validation.py`, `console_api.py` (`/console/brain-validation`), this doc.
