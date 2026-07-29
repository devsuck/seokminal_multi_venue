# Research Timeline (P78)

> Reconstructed entirely from existing append-only ledgers — **no new history database**.
> Read-only, deterministic.

## What it does — `jarvis/research_workflow/timeline.py` + `/console/research-timeline`
Walks the existing ledgers (`rwf_loops`, `rwf_runs`, `rwf_sessions`, `ring_ingestions`,
`expt_runs`, `rmi_lessons/failures/successes`, `ras_notes`) and maps each append-only record onto
the pipeline stages:

```
Idea → Hypothesis → Experiment → Backtest → Validation → Failure → Lesson →
Portfolio Effect → Risk → Paper → Decision Memo → Human Review → Archive
```

Entries are `{timestamp, stage, source, ref, label}`, sorted deterministically by
(timestamp, stage-order, source, ref). An optional topic filters by text.

## Reuse & no-duplication
Reads only existing ledgers; adds no ledger, no store. The dashboard page
(`/research-os/timeline`) renders it as a vertical timeline reusing the console primitives; the
Cockpit embeds a compact strip.

## Validation
`test_integration_p78_85.py`: reconstructed from seeded records, topic filter, determinism.
Endpoint shape test. Live screenshot.

## Files
`jarvis/research_workflow/timeline.py`, `console_api.py` (endpoint),
`app/(console)/research-os/timeline/page.tsx`, `lib/console-api.ts`, this doc.
