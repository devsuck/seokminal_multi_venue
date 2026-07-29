# Long Term Research Memory Expansion (P157)

> Integration only — improves long-term research retrieval. **No new memory storage.** Read-only.

## What it does — `jarvis/research_workflow/institutional_memory_expansion.py`
`build_institutional_memory()` → **InstitutionalMemoryReport** reconstructing the existing `rmi_` memory by:

`research themes · market cycles · historical periods · successful studies · failed studies`

Themes are a deterministic classification lens (momentum/mean-reversion/value/volatility/supply-chain/macro);
periods are extracted from record text. Reuses `rmi_lessons/successes/failures`, `semantic_recall`, and
`learning_engine`. **It stores nothing new** — it re-indexes existing memory for better retrieval.

## Reuse & no-duplication
rmi_ + semantic_recall + learning_engine. No new memory storage.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p151_160.py`: themes/cycles/studies present, no new storage.

## Files
`jarvis/research_workflow/institutional_memory_expansion.py`, `console_api.py` (`/console/institutional-memory`), this doc.
