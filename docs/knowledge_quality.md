# Knowledge Quality Monitor (P139)

> Integration only — monitors the quality of accumulated knowledge. Read-only, no new store.

## What it does — `jarvis/research_workflow/knowledge_quality.py`
`build_knowledge_health()` → a **Knowledge Health Score** (0–100 + grade HEALTHY/FAIR/DEGRADED/EMPTY) from
four checks over `rmi_lessons`:

`duplicate lessons · outdated knowledge · contradictions · missing evidence`

Duplicates are detected by a normalized token signature; contradictions reuse `conflict_detection` (P135);
missing evidence counts lessons with empty evidence. The score penalizes each issue proportionally.

## Reuse & no-duplication
`rmi_lessons` + conflict_detection. No new store.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p131_140.py`: four checks present, valid grade.

## Files
`jarvis/research_workflow/knowledge_quality.py`, `console_api.py` (`/console/knowledge-health`), this doc.
