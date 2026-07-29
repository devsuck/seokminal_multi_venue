# Explainability Visualization (P71)

> Visualizes the P67 evidence chain as an interactive graph — reusing the existing design system.
> Nothing appears as a black-box decision. Read-only; the human decides.

## What it does — `app/(console)/research-os/explain/page.tsx`

Enter a topic → `GET /console/explainability` → the P67 `EvidenceChain` is rendered as an
**interactive vertical graph**:

```
Question → Experiments → Validation → Failure Memory → Council Opinions →
Portfolio Impact → Risk Analysis → Decision Memo
```

- **Chain graph** — 8 connected nodes, each clickable; the selected node highlights and its detail
  (label + real references) shows on the right. The final node is tinted by overall confidence.
- **Confidence breakdown** — the per-factor scoring (validation / council / risk / historical /
  paper) shown visually as a labeled table with the confidence badge.
- **Why this conclusion / Why it may be wrong / Alternative views / Missing evidence** — the four
  explanation panels, so the reasoning is fully inspectable.

Navigation from any node is supported (click to focus); confidence is shown visually.

## Reuse analysis

- Chain, breakdown, and explanation panels are built from `Panel`/`PanelHead`/`Badge` + design
  tokens — no charting library, no new component.
- Reuses the P67 `/console/explainability` endpoint (also consumed by the chat workspace).

## Design compliance

Responsive `lg:grid-cols-5` (chain 2 / detail 3), collapsing to one column on mobile. The chain
uses token-colored dots + connector lines (SVG-free, crisp in both themes). Heavy synthesis runs
only on submit (lazy). Selected-node state is local; theme-aware via `var(--c-*)`.

## Honesty by construction

With empty memory the graph still renders all 8 stages and correctly reports LOW confidence,
"INSUFFICIENT BASIS", and the missing-evidence list (no paper confirmation, no precedent) — the
UI never fabricates certainty it doesn't have.

## Validation

`test_research_os_dashboard_endpoint.py`: explainability chain shape (8 stages, edges = stages−1,
breakdown + why-may-be-wrong present). Frontend `tsc` clean + `next build` + live screenshot.

## The vision, realized

P68–P71 make every capability built through P67 **visible, understandable, and actionable** in the
dashboard: the Operating Console summarizes the day, the Workflow board shows orchestration and
manages sessions, the Chat workspace is the primary interface, and this Explainability graph makes
every conclusion traceable — while the human keeps every decision.

## Files

Frontend `research-os/explain/page.tsx`, `lib/console-api.ts` (getExplainability), this doc.
Backend `console_api.py` (`explainability`).
