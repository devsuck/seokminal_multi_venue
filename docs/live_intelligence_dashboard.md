# Live Intelligence Dashboard (P119)

> Integration only — extends the Research OS console. Read-only. Reuses existing dashboard components.

## What it does
New page `/research-os/live-intelligence` (Research OS nav → *Live Intelligence*) over the unified
`/console/live-intelligence` endpoint (`jarvis/research_workflow/live_intelligence.py`). Four sections:

1. **Data Sources** — provider status / configured / coverage by category (from the P111 catalog + health).
2. **Market Feed** — events / news / earnings collected through the pipelines.
3. **Research Queue** — generated opportunity candidates (research ideas, never trade signals).
4. **Data Health** — API/data quality (`DataHealthReport`): availability ratio, issue count, status.

The market feed and research queue run on a labelled demo until live data sources are connected; provider
status and data health are real projections of the catalog + env configuration.

## Reuse & no-duplication
`providers` (P112), `research_feed` (P117), `data_quality` (P118); existing console primitives/widgets.
No new store.

## Governance
Every payload `is_advisory=True`, `is_decision=False`. No automatic trading/execution/allocation.

## Files
`app/(console)/research-os/live-intelligence/page.tsx`, `lib/console-api.ts` (`getLiveIntelligence`),
`components/console/CommandRail.tsx`, `jarvis/research_workflow/live_intelligence.py`, `console_api.py`, this doc.
