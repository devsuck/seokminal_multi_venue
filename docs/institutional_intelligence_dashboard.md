# Institutional Intelligence Dashboard (P159)

> Integration only — extends the Research OS console. Read-only. Reuses existing components.
> (Distinct from P149's `institutional_dashboard.md`.)

## What it does
New page `/research-os/intelligence` (Research OS nav → *Intelligence*) over
`/console/institutional-intelligence`. Seven sections:

1. **Data Production Health** — provider availability + quality (P151)
2. **Market Intelligence** — regime + labels
3. **Sector Intelligence** — key entities, risk factors, research questions (P152)
4. **Macro Context** — macro state, indicators, affected assets (P153)
5. **Company Intelligence** — relationships + risks (P154)
6. **Knowledge Context** — knowledge health (P139)
7. **Quality Scores** — the five intelligence-quality dimensions + confidence (P158)

## Reuse & no-duplication
data_production, sector/macro/company intelligence, knowledge_quality, intelligence_quality, and the
existing console primitives/widgets. No new store.

## Governance
`is_advisory=True`, `is_decision=False`. Advisory only; no prediction/ranking/allocation, no trading/execution.

## Files
`app/(console)/research-os/intelligence/page.tsx`, `lib/console-api.ts` (`getInstitutionalIntelligence`),
`components/console/CommandRail.tsx`, `console_api.py`, this doc.
