# Fundamental Intelligence (P115)

> Integration only — connects financial statements / earnings / valuation into research candidates. Read-only.

## Flow
`Financial Data → Earnings Intelligence → Research Candidate`

## What it does — `jarvis/research_workflow/fundamental_pipeline.py`
`run(financials, *, source)` maps financial/valuation records into `earnings_intelligence.analyze_earnings`
(P100) and emits research candidates with surprise, strategy impact, and historical comparison. Supported
metrics: **Revenue · EPS · Margin · Cashflow · Debt · Growth**.

## Reuse & no-duplication
`earnings_intelligence.analyze_earnings` (P100) → `recall`. No new store/engine.

## Governance
`is_advisory=True`, `is_decision=False`, `is_trade_signal=False`, `requires_human_review=True`.

## Validation
`test_integration_p111_120.py`: research candidate, positive surprise, supported metrics.

## Files
`jarvis/research_workflow/fundamental_pipeline.py`, `console_api.py` (`/console/live-intelligence`), this doc.
