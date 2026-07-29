# Paper Trading Feedback Loop (P63)

> Governed by `docs/CONSTITUTION.md` and the P53–P55 pipeline docs.
> **Integration over expansion** — added *inside* `research_ingestion` alongside
> `backtest_adapter`; persists through the shared `rmi_` memory. NO new database.
> **Paper trading only.** This module does NOT run paper trades — it *consumes their results*.
> No live broker, no execution, no capital allocation.

## Problem it fixes

The pipeline learned `Backtest → memory`. Reality diverges from backtests. P63 closes the loop:
`Backtest → Paper trading → performance observation → comparison → learning`.

## What it does — `jarvis/research_ingestion/paper_feedback.py`

`PaperTradingFeedback` (deterministic; takes paper *result dicts* as input — never executes):

### Difference analysis — `compare(backtest_expected, paper_actual)`
Computes `return_gap`, `sharpe_gap`, `drawdown_gap`, `gap_ratio`, and a **deterministic cause**:
- return shortfall + higher paper cost/turnover → *"Higher transaction impact — backtest
  underestimated liquidity cost"*
- worse realized drawdown → *"regime/risk underestimated"*
- outperformance → *"verify not a small-sample artifact"*

> Example — Backtest expected 15%, paper actual 4% → cause "underestimated liquidity cost",
> severity HIGH.

### Feedback record — `record_feedback(strategy, backtest, paper, experiment_id, risk_ref, …)`
Writes the observation as an `rmi_` **lesson** linking **Experiment · Strategy · Risk · Lesson**,
tagged with the `PAPER vs BACKTEST` marker. A severe shortfall (`gap_ratio ≤ −0.5`) also records
an `rmi_` **failure**, so `failure_intelligence()` picks it up. No new store.

### Assistant answer — `did_it_work_outside_backtest(topic)`
Reuses `ResearchAssistantEngine.recall()` and filters for the paper marker, answering
**"Did this strategy work outside backtest?"** with the paper observations found.

## Memory integration & the assistant

Because everything lands in `rmi_`, `recall("<strategy>")` returns the paper observation, the
assistant can answer *"How did this strategy perform after backtest?"*, and severe shortfalls
appear in failure intelligence — no new query path required.

## Validation & safety

Append-only + hash-chained (`rmi_`); deterministic; advisory; **paper-only** — no
`execute/trade/deploy/allocate/approve`, no broker/execution/live imports, does not import or
call any execution path (AST-scanned).

## Tests (`research_ingestion/tests/test_paper_feedback.py`, 12)

cost-cause difference · gap ratio · outperformance · **lesson+failure on severe shortfall** ·
lesson-only on small gap · **`did_it_work_outside_backtest` finds paper evidence** · no-evidence
case · failure intelligence sees the shortfall · advisory · dry-run no write · safety scans.

## Files

`research_ingestion/paper_feedback.py` (new), `research_ingestion/__init__.py` (exports),
`tests/test_paper_feedback.py` (new), this doc.
