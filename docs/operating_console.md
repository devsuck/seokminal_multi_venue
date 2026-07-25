# Hedge Fund Operating Console (P70)

> A single daily executive overview of the whole research organization — built on the existing
> console design system. Read-only, advisory; the human decides.

## What it does — `app/(console)/research-os/console/page.tsx`

`GET /console/operating-console` aggregates every P56–P67 subsystem into one summary, rendered as
KPI tiles + panels (auto-refresh every 60s):

| Section | Source |
|---|---|
| **Today's Research** | assistant daily/experiment summary (records, runs, sources) |
| **Today's Opportunities** | P58 research queue proposals (name, kind, EV, confidence, reason) |
| **Today's Risks** | P62/failure-intelligence categories (bar chart) + top lessons |
| **Today's Events** | P60 supply-chain relationship-graph size (monitored map) |
| **Today's Portfolio Exposure** | paper capital, gross exposure %, positions (Meter) |
| **Today's Paper Trading** | paper_execution portfolio value + PnL |
| **Today's Active Sessions** | P66 session cards (pending/done/open-question counts) |
| **Today's Recommendations** | P59 council recommendation for the top opportunities |

Everything is summarized into one executive overview, exactly as the mission specifies.

## Reuse analysis

- KPI row uses `StatTile`; sections use `Panel`/`PanelHead`/`Badge`/`Meter`/`KV` — no new components.
- One new read-only endpoint composing existing engines; no new engine, no duplicate API.
- `useConsole(..., 60000)` reuses the existing polling hook for quiet auto-refresh.

## Design compliance

Responsive: `grid-cols-2 md:grid-cols-4` KPIs, `lg:grid-cols-2` panel grid, `md/lg:grid-cols-3`
session cards. Design tokens → dark/light. Risk bars scale to the max category; empty states
everywhere (production memory starts empty, so tiles read 0 honestly).

## Validation

`test_research_os_dashboard_endpoint.py`: operating-console sections present, advisory flag,
read-only. Frontend `tsc` clean + `next build` compiles + live screenshot captured.

## Remaining gaps

- Sector/country exposure breakdown is not yet wired (paper positions lack a sector map); the
  console shows gross exposure only.
- Events section shows the static supply-chain map size, not live incoming events (no live event
  feed in this environment).

## Files

Backend `console_api.py` (`operating-console`). Frontend `research-os/console/page.tsx`,
`lib/console-api.ts` (getOperatingConsole), this doc.
