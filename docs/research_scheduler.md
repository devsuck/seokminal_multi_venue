# Research Operation Scheduler (P141)

> Integration only — manages recurring research cycles. **No automatic investment action.** Read-only.

## What it does — `jarvis/research_workflow/research_scheduler.py`
`ResearchScheduler.plan_cycle(cycle_type)` → **ResearchOperationPlan**
`{cycle_type, tasks, assigned_agents, status, human_review_required}`.

Cycles (deterministic cadence + task set):
- **daily** — morning_briefing, company_monitor, opportunity_scan, review_queue_refresh
- **weekly** — strategy_health, weekly_letter, knowledge_health, conflict_scan
- **monthly** — strategy_review, agent_performance, research_accuracy, memory_audit

Flow: Schedule → Research Director (agent assignment) → Research Tasks → Review Queue. There is **no
background loop** — it is a deterministic plan generator; the cadence is metadata and periodic invocation is
external (cron/human). `auto_execution: False`.

## Reuse & no-duplication
`research_director` (P122) for assignment. No new ledger/scheduler engine.

## Governance
`is_advisory=True`, `is_decision=False`, `human_review_required=True`. No automatic investment action.

## Validation
`test_integration_p141_150.py`: all plan fields, no auto-execution, weekly/daily cycles.

## Files
`jarvis/research_workflow/research_scheduler.py`, `console_api.py` (`/console/research-schedule`), this doc.
