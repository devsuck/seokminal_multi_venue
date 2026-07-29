# Research Director Agent (P122)

> Integration only — receives research objectives, plans, and assigns specialists. **No investment recommendation.**

## What it does — `jarvis/research_workflow/research_director.py`
`ResearchDirector.plan(objective)` → **Research Plan**
`{objective, hypothesis, required_data, assigned_agents, validation_plan}`.

Responsibilities: receive objective, select workflow, assign specialist tasks, track progress, summarize.
- hypothesis from `hypothesis_generator` (P73)
- priority from `research_prioritizer` (P76)
- required_data + validation_plan from `experiment_planner` (P74)
- deterministic specialist assignment (always includes Critic + Writer)

`track(objective)` records progress through the existing `session_manager` (rwf_sessions) — no new ledger,
`commit=False` = preview.

## Reuse & no-duplication
hypothesis_generator, experiment_planner, research_prioritizer, session_manager. No new memory.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`. No investment recommendation.

## Validation
`test_integration_p121_130.py`: all Research Plan fields, Critic+Writer assigned, determinism.

## Files
`jarvis/research_workflow/research_director.py`, `console_api.py` (`/console/agent-workspace`), this doc.
