# Research Agents Dashboard (P129)

> Integration only — extends the Research OS console. Read-only. Reuses existing components.

## What it does
New page `/research-os/agents` (Research OS nav → *Research Agents*) over `/console/agent-workspace`
(`multi_agent_workflow.run`). Sections:

1. **Active Research** — objective + the Director→Analyst→Strategy→Critic→Writer pipeline
2. **Agent Status** — per-agent role + stage completion
3. **Current Tasks** — the Director's specialist assignments
4. **Generated Reports** — Research Report (7 sections + confidence + limitations)
5. **Critic Feedback** — reviewer verdict, dimensions, quality
6. **Human Review Queue** — items needing human action

The workspace runs a labelled demo objective until a user supplies one.

## Reuse & no-duplication
All P121–128 agents; existing console primitives/widgets. No new store.

## Governance
`is_advisory=True`, `is_decision=False`. Analysis only; no trading/execution.

## Files
`app/(console)/research-os/agents/page.tsx`, `lib/console-api.ts` (`getAgentWorkspace`),
`components/console/CommandRail.tsx`, `console_api.py`, this doc.
