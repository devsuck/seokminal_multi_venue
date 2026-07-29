# Conversational Research Workspace (P69)

> The chat interface becomes the primary operating interface — reusing the existing console
> design system. Read-only, analysis/recall only; the human decides.

## What it does — `app/(console)/research-os/chat/page.tsx`

One question fans out to three existing read-only endpoints in parallel and composes them into
a single research turn:

```
question ─┬─▶ GET /console/decision-memo   → recommendation, supporting/counter, unknowns, next
          ├─▶ GET /console/explainability  → referenced experiments, confidence
          └─▶ GET /console/assistant       → memory recall answer + topic
```

The workspace shows exactly what the mission asks:

- **Conversation** — the question + recommendation, plus a rolling history.
- **Recommendation** — decision-memo recommendation + rationale, with a confidence badge.
- **Supporting vs Counter** — the council's supportive and cautionary arguments side by side.
- **Memory Recall** — the assistant's recall answer for the topic.
- **Referenced Experiments** — real experiment ids from the evidence chain (`references_experiments`).
- **Suggested Actions** — decision-memo `suggested_next_research`, each clickable to ask again.
- **Remaining Unknowns** — surfaced when validation/paper confirmation is missing.

Preset prompts include **"Continue yesterday's research"**, matching the P66 session-continuity vision.

## Reuse analysis

- Built entirely from `PageHeader`, `Panel`, `PanelHead`, `Badge` — no new components.
- Uses existing `getAssistant` plus the new `getDecisionMemo` / `getExplainability` clients.
- No new backend endpoint — reuses P65/P67 surfaces and the existing assistant endpoint.

## Design compliance

Design tokens for dark/light; responsive `lg:grid-cols-3` (conversation 2 / context 1) collapsing
to one column on mobile; heavy synthesis (memo + evidence) fetched only on submit (lazy).

## Validation

Frontend `tsc` clean + `next build` compiles. Backend memo/explainability shapes covered by
`test_research_os_dashboard_endpoint.py` (decision-memo sections, explainability chain).

## Remaining gaps

- No streaming — answers arrive as a single synthesized turn (the engines are deterministic, not
  token-streamed).
- "Continue yesterday's research" recalls memory/decisions but does not yet auto-open the matching
  P66 session; that link is a follow-up.

## Files

`app/(console)/research-os/chat/page.tsx`, `lib/console-api.ts` (getDecisionMemo/getExplainability),
this doc.
