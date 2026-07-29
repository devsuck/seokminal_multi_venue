# Workflow Orchestrator (P64)

> Governed by `docs/CONSTITUTION.md`.
> **Orchestration, not new intelligence.** Coordinates existing subsystems; creates no
> duplicate engine and no duplicate ledger. Read-only, deterministic, human-approved, append-only.
> No trading, no execution.

## Problem it fixes

Jarvis had Research Memory, Queue, Council, Portfolio, Risk, and Paper feedback — but they ran
independently. P64 adds a coordination layer that drives them through one coherent pipeline.

## Pipeline (`jarvis/research_workflow/orchestrator.py`)

```
Request → Queue → Recall → Council → Design → Backtest → Validation →
Portfolio → Risk → Paper → Decision → Human Decision
```

Each stage **calls an existing engine** (read-only): Queue→`ResearchQueueEngine`,
Recall→`ResearchAssistantEngine.recall`, Council→`ResearchCouncilEngine`,
Validation→`research_ingestion.validate_backtest`, Portfolio→`PortfolioIntelligence`,
Risk→`StrategyRiskReasoner`, Paper→`PaperTradingFeedback.compare`, Decision→`DecisionSupportEngine`.

**External-input stages** (Design, Backtest, Paper) are **not executed** by the orchestrator —
if their result isn't in the context, the stage is `BLOCKED` (partial completion). Jarvis never
runs a backtest or a trade.

## Execution model — event-sourced, append-only

Every stage emits a `StageEvent` to the `rwf_runs` hash-chained ledger. State is a deterministic
fold over events, so:

- **Partial completion** — stops at the first `BLOCKED`/`PENDING` stage.
- **Resume** — `resume(run_id, …)` restarts at the first non-completed stage; once the missing
  input is supplied, `Design`→`Decision` complete. Completed stages are never re-run.
- **Retry** — `retry(run_id, stage, …)` re-drives from a chosen stage.
- **Cancel** — `cancel(run_id)` writes a terminal `CANCELLED` event; further run/resume/retry raise.
- **Deterministic logs** — `execution_log` records `{stage, status, note, output_digest}` per event.
- **Dry-run** — `commit=False` returns the same state preview with zero writes.

## Human decision — mandatory, never automated

The terminal `HUMAN_DECISION` stage is `PENDING` until `record_human_decision(run_id, decision,
reviewer)` — **`reviewer` is required** (empty raises); the engine exposes no approve/execute.
`requires_human_decision` stays `True` until a human records it.

## Reuse & no-duplication

Reuses six existing engines by injection. The only new storage is `rwf_runs` / `rwf_sessions`
(orchestration state) — **no experiments/failures/portfolio/risk ledger is duplicated**; those
stay owned by their packages. Test asserts orchestration writes only `rwf_*`.

## Tests (`tests/test_orchestrator.py`, 17)

full orchestration · deterministic log · partial completion (BLOCKED at Design) · **resume after
input** · resume doesn't re-run completed · retry · cancel blocks further · **human decision
requires reviewer** · records human decision · hash chain valid · **no duplicate ledgers** ·
dry-run no writes · advisory · forbidden-import/def/leak scans.

## Files

`research_workflow/{orchestrator,models,ledger,verify,__init__,__main__}.py`, `tests/…`, this doc.
