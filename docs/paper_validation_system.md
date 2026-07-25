# Paper Validation System (P103)

> Integration only — upgrades the existing paper-feedback loop into a validation **monitor**.
> Purpose: **detect backtest success but paper failure.** Read-only, deterministic, no new store.

## What it does — `jarvis/research_workflow/paper_validation.py`
`PaperValidationMonitor.monitor(backtest, paper, *, benchmark=None)` → **PaperValidationReport**.
Tracks six dimensions, expected vs actual with a gap each:

`return · volatility · drawdown · turnover · exposure · benchmark_difference`

It reuses `PaperTradingFeedback.compare` (P63) for the return/sharpe/drawdown difference, cause, and
severity, and computes the remaining dimensions from the paper metrics.

`status` is deterministic:
- `BACKTEST_SUCCESS_PAPER_FAILURE` — backtest positive but paper < 50% of expected
- `DIVERGENCE` — high-severity difference
- `CONSISTENT` / `INSUFFICIENT_DATA`

## Reuse & no-duplication
`PaperTradingFeedback.compare` (P63). Learning is written through the existing paper-feedback path into
the `rmi_` ledgers — no new store, no execution.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p101_110.py`: detects backtest-success/paper-failure, all six tracked metrics present,
determinism.

## Files
`jarvis/research_workflow/paper_validation.py`, `console_api.py` (`/console/validation-loop`), this doc.
