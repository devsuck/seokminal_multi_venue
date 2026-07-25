# AI Research Workspace (P80)

> The conversational workspace as one place that exposes every research surface. Reuses every
> existing backend engine; no duplicated business logic. Read-only; the human decides.

## What it does
The existing `/research-os/chat` workspace (P69) already fans one question out to
decision-memo + explainability + memory recall and shows conversation, recommendation,
supporting/counter arguments, referenced experiments, suggested actions, and remaining unknowns.
P80 completes it by making the Cockpit and the new endpoints reachable as one connected surface:

| Panel | Source (reused) |
|---|---|
| Conversation / Recommendation | `/console/decision-memo` (P65) |
| Memory Recall | `/console/assistant` (P44) |
| Failure Intelligence | `/console/failure-intel` (P56/P62) |
| Decision Memo · Evidence Chain | `/console/decision-memo`, `/console/explainability` |
| Research Timeline · Knowledge Graph | `/console/research-timeline`, `/console/research-graph` |
| Portfolio / Risk / Paper Context | cockpit aggregation (`/console/cockpit`) |
| Current Workflow | `/console/research-workflow` (P68) |

## Reuse & no-duplication
No new endpoint and no new logic — the workspace and Cockpit compose the existing read-only
surfaces. Navigation links the chat, cockpit, timeline, graph, and explainability into one flow.

## Validation
`tsc` clean · `next build` · existing chat/decision/explainability endpoint tests.

## Remaining gaps
The panels live across the chat page + Cockpit rather than a single monolithic screen; a unified
tabbed workspace is a cosmetic follow-up (all data is already wired).

## Files
Existing `research-os/chat` + `research-os/cockpit` pages; this doc.
