# Strategy Research Agent (P125)

> Integration only — formulates hypotheses, designs experiments, analyzes historical research. Analysis only.

## What it does — `jarvis/research_workflow/strategy_researcher.py`
`StrategyResearcher.plan(topic)` → **Strategy Research Plan**
`{hypotheses, experiment, backtest_job, validation_plan, historical_research}`.

Uses `hypothesis_generator` (P73), `experiment_planner` (P74), `backtest_bridge` (P102, job left at
`WAITING_HUMAN` — no auto-execution), `paper_validation` (P103), `recall`+`mistake_check`.

## Reuse & no-duplication
Existing planning/validation engines. No new engine/memory. Backtest runs externally by a human.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p121_130.py`: plan type, experiment present, backtest job WAITING_HUMAN (no auto-execution).

## Files
`jarvis/research_workflow/strategy_researcher.py`, `console_api.py` (`/console/agent-workspace`), this doc.
