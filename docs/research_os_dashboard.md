# Research OS Dashboard (P68)

> Exposes the P64–P67 orchestration layer through the existing dashboard.
> **Reuse, don't rebuild.** Existing design system, primitives, rail, and `/console/*` client.
> Read-only except session management. Human decision preserved.

## What it adds

A dedicated **Research OS** nav group (CommandRail) with four workspaces:
Operating Console (P70), Workflow (P68), Research Chat (P69), Explainability (P71) —
all under the `(console)` route group at `/research-os/*`, using the shared shell.

## The Workflow workspace — `app/(console)/research-os/workflow/page.tsx`

Surfaces the orchestrator's live state from `GET /console/research-workflow`:

- **Active Research Workflows** — each run rendered as a **stage pipeline** (the 12 stages
  Request→…→Human) colored by status: COMPLETED (green), BLOCKED (amber), PENDING/human
  (cyan), CANCELLED (red). Shows blocked stage, human-decision gate, and completed count.
- **Research Sessions** — create / pause / resume / archive (the only mutating actions),
  with per-session pending/done/lessons counts and state badge.
- **Research Queue** — the P58 opportunity proposals.
- KPI tiles: runs · awaiting-human · active sessions · queue proposals.

## Backend — `GET /console/research-workflow`, `POST /console/session/{action}`

`research-workflow` folds the `rwf_runs` ledger into workflow states, lists sessions, and runs
the queue — all `_safe`-wrapped, read-only, advisory. `session/{action}` (create/pause/resume/
archive) is the **single mutating endpoint**; it writes only the append-only `rwf_sessions`
ledger — no trading, no execution.

## Reuse analysis

- **Components**: `Panel`, `PanelHead`, `StatTile`, `Badge`, `Meter`, `PageHeader`, `useConsole`
  — zero new primitives.
- **Client**: `lib/console-api.ts` extended with typed `getResearchWorkflow` + `sessionAction`
  (a new `post` helper) — no duplicate client.
- **API**: new read-only endpoints on the existing `/console` router — no duplicate API surface.
- **Nav**: one new rail group; existing route group and layout reused.

## Design compliance

Design tokens (`var(--c-*)`) → automatic dark/light. Responsive grids
(`grid-cols-2 md:grid-cols-4`, `lg:grid-cols-2`). Heavy data (queue/sessions) loads on mount;
the workflow view polls at 0 (manual refresh after actions). Empty states everywhere
(production `_state` starts empty).

## Validation

Backend: `api_server/tests/test_research_os_dashboard_endpoint.py` — workflow shape, 12 stages,
session lifecycle (create→pause→resume→archive) in an isolated ledger, unknown/missing-id
guards. Frontend: `tsc --noEmit` clean, `next build` compiles the routes.

## Remaining gaps

- Workflow **run/resume/cancel** are CLI-driven; the dashboard manages sessions and views runs
  but does not yet start/advance a run from the UI (kept minimal to avoid broad mutation).
- Production `_state` is empty, so live runs appear only after the backend records them.

## Files

Backend: `console_api.py` (+5 endpoints), `tests/…`. Frontend: `research-os/workflow/page.tsx`,
`lib/console-api.ts`, `components/console/CommandRail.tsx`, this doc.
