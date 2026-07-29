# Research Session Manager (P66)

> Governed by `docs/CONSTITUTION.md`.
> **Makes research persistent.** No new intelligence; event-sourced session state only.
> Read-only over knowledge ledgers, deterministic, append-only.

## Problem it fixes

Research was stateless between interactions. P66 gives it durable sessions so you can
**"continue yesterday's research"** from stored state.

## What it does — `jarvis/research_workflow/session_manager.py`

`ResearchSessionManager` — event-sourced lifecycle over the `rwf_sessions` hash-chained ledger:

- `create_session(goal, goals=…)` → `ACTIVE`
- `update_progress(session, progress, pending, completed_experiments, lessons, open_questions,
  resolved_questions, …)` — records a `PROGRESS` event
- `pause_session` → `PAUSED` · `resume_session` → `ACTIVE` (returns the **full stored state**)
- `archive_session` → `ARCHIVED`
- `state(session)` folds events into a `SessionState` tracking **goals · progress · pending work ·
  completed experiments · lessons learned · open questions**
- `list_sessions()` summarizes all

### State-fold semantics
Lists accumulate append-only with de-duplication; **completed experiments are removed from
pending work**; **resolved questions are removed from open questions** — so the tracked state
stays accurate over time. Each event stores its payload inline (append-only) so state is fully
reconstructable — the basis for "continue yesterday's research."

## Reuse & no-duplication

Experiments, lessons, and knowledge remain in their existing ledgers (`expt_`, `rmi_`). This
package stores only **session coordination state** in `rwf_sessions` — no duplicate knowledge store.

## Tests (`tests/test_session_manager.py`, 10)

create · track all six tracked fields · completed removed from pending · resolved removed from
open · **pause then resume preserves pending work + lessons ("continue yesterday")** · archive ·
list · hash chain valid · dry-run no write · advisory.

## Files

`research_workflow/session_manager.py` (+ shared `models.py`/`ledger.py`), `tests/…`, this doc.
