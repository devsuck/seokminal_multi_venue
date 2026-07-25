# Executive Research Cockpit (P85)

> The final home screen — one integrated view of every capability built through P76. Reuses all
> orchestration modules; read-only; centered on human decision.

## What it does — `jarvis/research_workflow/cockpit.py` + `/console/cockpit`
Aggregates (read-only) into one payload: **Today's Research · Current Loop · Top Opportunities ·
Highest Risks · Portfolio Exposure · Research Health · Knowledge Growth · Paper Performance ·
Timeline · Knowledge Graph · Research Queue · Human Review Queue · Recent Sessions ·
Quick Resume**. It composes the P78/P79/P81/P58/P62/P66 surfaces — no new logic.

The dashboard page `/research-os/cockpit` is the **primary dashboard**: KPI row + Current Loop +
Health coverage meters + Highest Risks + a reconstructed Timeline strip + Opportunities + Human
Review Queue + Quick Resume + exposure, auto-refreshing every 60s.

## Reuse & no-duplication
Every section reuses an existing module/endpoint. No new engine, no new ledger, no new API logic.

## Validation
`test_integration_p78_85.py`: cockpit aggregates all keys, advisory. `/console/cockpit` shape
test. Live screenshot (HEALTH 87.2, populated timeline/risks/opportunities).

## The vision, realized
Jarvis now operates as a complete Research Operating System: every P1–P76 capability is visible,
connected (timeline + knowledge graph), explainable (evidence chains), and centered on human
decision — integration over expansion throughout.

## Files
`jarvis/research_workflow/cockpit.py`, `console_api.py`,
`app/(console)/research-os/cockpit/page.tsx`, `lib/console-api.ts`, `CommandRail.tsx`, this doc.
