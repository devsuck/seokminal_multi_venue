# Multi-Agent Research Workflow (P128)

> Integration only — connects the agents into one research pass. Analysis only. Existing ledgers only.

## Chain
`Director → Analyst (Market/Company) → Strategy Researcher → Critic (Reviewer) → Writer`

## What it does — `jarvis/research_workflow/multi_agent_workflow.py`
`run(objective, company, events, financials, headlines, commit=False)` executes the five-agent chain and
returns the director plan, specialist memos, review, report, and a human review queue.

Progress is tracked via `session_manager` (rwf_sessions) and an advisory summary via
`ResearchAssistantEngine.record_advisory` (ras_notes) — **existing ledgers only**, `commit=False` = preview.
No new memory.

## Reuse & no-duplication
All P122–127 agents + research_workflow orchestration (session_manager, record_advisory). No new ledger.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`. Human makes every decision.

## Validation
`test_integration_p121_130.py`: five-stage pipeline, writes to existing ledgers only, ledger stays 3.

## Files
`jarvis/research_workflow/multi_agent_workflow.py`, `console_api.py` (`/console/agent-workspace`), this doc.
