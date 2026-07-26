# Jarvis Research OS v1.5 Validation (P150)

> Validation of the operational research firm. Read-only, deterministic, no execution.
> (Distinct from the P120 `operational_validation.md`; module: `ops_validation.py`.)

## The loop
`External Data → Research Opportunity → Agent Research → Experiment → Validation → Knowledge Update → Future Research Improvement`

## What it verifies — `jarvis/research_workflow/ops_validation.py`
`validate_research_ops()` runs seven checks:
1. **scheduler_works** — a research operation plan is produced, no auto-execution
2. **agents_complete_research_tasks** — the multi-agent workflow completes with a report
3. **reports_generated** — the 8-section report is produced with confidence
4. **knowledge_updates_correctly** — learning routes to rmi_lessons (preview)
5. **human_review_required** — every stage keeps a human-review flag, `is_decision=False`
6. **no_duplicate_systems** — ledger stays 3; ops modules never write ledgers directly (AST)
7. **safety_rules_pass** — AST scan for forbidden defs/imports

`ops_safety()` confirms no new database/ledger/memory-store/execution-engine, no
`execute/trade/place_order/allocate/approve`, no broker/capital management.

## Result
All seven checks pass; safety clean; ledger stays 3.

## Validation
`test_integration_p141_150.py`: seven checks, safety no-new-ledger.

## Files
`jarvis/research_workflow/ops_validation.py`, `console_api.py` (`/console/research-ops-validation`), this doc.
