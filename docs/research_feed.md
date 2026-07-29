# Research Feed Scheduler (P117)

> Integration only — periodically collects available information into the research loop.
> **No automatic investment action.** Read-only, deterministic.

## Flow
`Data Source → Event → Research Trigger → Opportunity Queue`

## What it does — `jarvis/research_workflow/research_feed.py`
`ResearchFeedPipeline(interval_seconds, max_retries).collect(sources)` takes `{category: raw_list}`, and for
each category:
- **source health check** via `providers.provider_for(category).health_check()`
- **retry handling** — deterministic retry wrapper (up to `max_retries`)
- normalizes through the P113–116 pipelines
- **duplicate prevention** — content-hash dedup (`dropped_duplicates`)
- routes each fresh event through `research_trigger.dispatch` (P101) into an **opportunity queue**

There is **no background loop** — it is a deterministic single pass; the interval is metadata and periodic
invocation is external (cron/human). `schedule()` reports `auto_execution: False`.

## Reuse & no-duplication
`providers` (P112), P113–116 pipelines, `research_trigger.dispatch` (P101), `opportunity_discovery` (P88).
No new store/ledger.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`. No automatic investment action.

## Validation
`test_integration_p111_120.py`: dedup + opportunity queue, health/retry config, no auto-execution.

## Files
`jarvis/research_workflow/research_feed.py`, `console_api.py` (`/console/research-feed`), this doc.
