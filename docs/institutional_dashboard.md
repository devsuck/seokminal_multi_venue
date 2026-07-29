# Institutional Research Dashboard (P149)

> Integration only — extends the Research OS console with the Research Organization dashboard. Read-only.

## What it does
New page `/research-os/organization` (Research OS nav → *Research Org*) over `/console/research-organization`.
Sections:

1. **Market Overview** — regime, opportunities, risk factors (from the morning briefing, P142)
2. **Company Monitoring** — company events, impact, research priority (P143)
3. **Strategy Health** — per-strategy health scores + review-needed count (P144)
4. **Agent Status** — per-agent effectiveness (P148)
5. **Knowledge Health** — knowledge health score (P139)
6. **Research Reports** — agent outputs
7. **Review Queue** — items needing human action (P146)

Plus an operational status banner (P150 v1.5).

## Reuse & no-duplication
morning_briefing, company_monitor, strategy_health, agent_performance, knowledge_quality, research_workspace,
ops_validation; existing console primitives. No new store.

## Governance
`is_advisory=True`, `is_decision=False`. Advisory only; no trading/execution/allocation.

## Files
`app/(console)/research-os/organization/page.tsx`, `lib/console-api.ts` (`getResearchOrganization`),
`components/console/CommandRail.tsx`, `console_api.py`, this doc.
