# Autonomous Runtime Dashboard (P77)

> Integration & visualization only — exposes the existing P72–P76 autonomous runtime in the
> dashboard. Reuses the Research OS UI components and the `/console/autonomous-runtime` endpoint.
> Read-only; the only mutation permitted is where already allowed. Human checkpoints preserved.

## What it adds — `app/(console)/research-os/autonomous/page.tsx`
- **Active Loops** board — each loop rendered as the 9-stage pipeline (Idea→…→Next) colored by
  status, with PAUSED / BLOCKED / CHECKPOINT badges and its audit trail.
- **Ranked Hypotheses** (P73+P76), **Recommended Experiment** spec (P74), **Critic** verdict with
  the 8 dimensions and severities (P75) — a live preview for any topic.
- KPI: loops · awaiting human checkpoints.

## Reuse
`Panel/PanelHead/StatTile/Badge` primitives; the existing `/console/autonomous-runtime` endpoint
(built in P72–76). No new component, no new endpoint, no business logic in the page.

## Validation
`tsc` clean · `next build` compiles `/research-os/autonomous` · live screenshot. Backend shape
covered by `test_research_os_dashboard_endpoint.py`.

## Files
`app/(console)/research-os/autonomous/page.tsx`, `lib/console-api.ts` (getAutonomousRuntime),
`components/console/CommandRail.tsx`, this doc.
