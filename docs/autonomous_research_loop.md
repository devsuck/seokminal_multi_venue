# Autonomous Research Loop (P72)

> Governed by `docs/CONSTITUTION.md`. Orchestration over expansion — added inside
> `research_workflow` (the reuse target), composing existing engines. Deterministic,
> reproducible, append-only, human-checkpointed. **AI proposes, critiques, prioritizes, learns —
> it never executes, allocates, or approves.**

## What it is

A deterministic loop that turns an idea into a self-improving research cycle:

```
Idea → Hypothesis → Experiment Design → Backtest → Validation →
Failure Analysis → Lesson → Updated Hypothesis → Next Experiment
```

Each stage **calls an existing engine** — no new intelligence:

| Stage | Engine (reused) |
|---|---|
| Hypothesis | `HypothesisGenerator` (P73) + `ResearchPrioritizer` (P76) to pick the top |
| Experiment Design | `ExperimentPlanner` (P74) |
| Backtest | **external input** — human checkpoint; not executed |
| Validation | `research_ingestion.validate_backtest` |
| Failure Analysis | `ResearchCritic` (P75) |
| Lesson | `research_memory_intelligence.record_lesson` (rmi_) |
| Updated Hypothesis | derived from the critique → stored via P73 |
| Next Experiment | `ResearchPrioritizer.recommend_next` (P76) |

## Execution model — event-sourced, auditable, resumable

Every stage emits a `LoopEvent` (with its artifact payload inline) to the append-only,
hash-chained `rwf_loops` ledger. State is a deterministic fold:

- **Human checkpoint** — `Backtest` is external; with no result the loop stops `BLOCKED` (the AI
  never runs a backtest or a trade).
- **Resume** — `resume(loop_id, …)` continues from the first non-completed stage once the backtest
  result is supplied; completed stages are read from their persisted payloads (not re-generated),
  so resume is deterministic even though hypotheses were stored to memory mid-loop.
- **Pause / Cancel** — `pause` records an audit event; `cancel` is terminal and blocks resume.
- **Audit trail** — `audit_trail` lists every stage/status/note; `artifacts` exposes the
  hypothesis, spec, critique, validation, lesson, and next recommendation.
- **Determinism** — same idea + context → identical stages, identical `spec_hash`, identical
  `next` (verified in dry-run).

The loop **never accepts research automatically**: `requires_human_checkpoint` stays true, and a
critic BLOCK feeds Failure Analysis → Lesson → Updated Hypothesis (learning), never a deployment.

## Integration & reuse analysis

Reuses P73/P74/P75/P76 (all new sibling modules), `research_ingestion` validation, `rmi_` memory,
`research_assistant` recall (via the sub-engines). **No new package, no new engine.** The only new
storage is `rwf_loops` (loop coordination state) — a new record type, not a duplicate of any
knowledge ledger. Existing `research_workflow` (orchestrator/sessions/decision/explainability)
remains compatible (its ledger-tuple test updated for the additive ledger).

## Validation

`tests/test_critic_prioritizer_loop.py`: blocks-on-backtest, full 9-stage pipeline, determinism,
resume-after-backtest, lesson persisted, audit-trail hash chain, pause/cancel, dry-run no-write.

## Files

`research_workflow/autonomous_loop.py` (+ `ledger.py` LOOPS, `models.py` loop ids/stages), tests,
this doc. Surfaced read-only via `GET /console/autonomous-runtime`.

## Remaining gaps

- Backtest execution stays external (by design — no auto-execution); wiring it to the real
  `backtest_runner` behind an explicit human trigger is a follow-up.
- Multi-iteration looping (Next → new loop) is manual; the loop produces the next recommendation
  but does not auto-spawn the following iteration.

## Next recommended phase

**P77 — Autonomous Runtime Console**: a dashboard workspace over `/console/autonomous-runtime`
(loop board + hypothesis/critique/priority preview), reusing the P68–P71 UI patterns.
