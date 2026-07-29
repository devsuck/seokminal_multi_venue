# Research Quality Score (P84)

> Scores every research project across 13 dimensions, deterministically. Read-only, no new store.

## What it does — `jarvis/research_workflow/quality_score.py` + `/console/research-quality`
`score_research(backtest)` returns 0..1 scores for **reproducibility · walk-forward ·
random baseline · out-of-sample · transaction cost · liquidity · failure learning ·
portfolio impact · paper performance · evidence · documentation · confidence**, and a weighted
**overall quality** (0–100) with an A–D grade. Inputs are validated with
`research_ingestion.validate_backtest`; evidence/failure-learning reuse `recall`/`mistake_check`.

The endpoint reconstructs a strategy's metrics from the experiment ledger (`expt_results`) and
scores it — no metrics are fabricated.

## Reuse & no-duplication
Reuses validation + recall + the critic's thresholds; adds no store, no engine.

## Validation
`test_integration_p78_85.py`: all 12 dimensions present, overall in [0,100], grade valid,
determinism, complete>incomplete. Endpoint test.

## Files
`jarvis/research_workflow/quality_score.py`, `console_api.py`, this doc.
