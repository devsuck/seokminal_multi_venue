# Agent Effectiveness Analysis (P148)

> Integration only — measures agent effectiveness to improve the research process. **Not autonomous self-modification.**

## What it does — `jarvis/research_workflow/agent_performance.py`
`AgentPerformanceMonitor.report()` scores each agent deterministically from a multi-agent workflow output:
- **ResearchDirector** — task quality (assignment + hypothesis + validation plan)
- **Analyst Agents** — evidence quality (events/fundamentals gathered)
- **ResearchReviewer** — issue detection (critique dimensions + verdict)
- **ResearchWriter** — report usefulness (sections + confidence + limitations)

Output: **Agent Performance Report** with per-agent scores, overall effectiveness, and improvement
suggestions for humans to act on. `autonomous_self_modification: False` — the agents are never changed by
this; it informs human process improvement only.

## Reuse & no-duplication
multi_agent_workflow (P128) output. No new store.

## Governance
`is_advisory=True`, `is_decision=False`. Not autonomous self-modification.

## Validation
`test_integration_p141_150.py`: four agents scored, not self-modifying.

## Files
`jarvis/research_workflow/agent_performance.py`, `console_api.py` (`/console/agent-performance`), this doc.
