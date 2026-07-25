# Opportunity Discovery Engine (P88)

> Integration only — discovers abnormal situations as **research ideas**. **Never a trade signal.**
> Reuses hypothesis generator + recall + event intelligence. Deterministic, read-only.

## What it does — `jarvis/research_workflow/opportunity_discovery.py` + `/console/opportunity-queue`
`discover(signals)` turns detected anomalies into **Opportunity Objects** —
`{title, reason, evidence, historical_similarity, related_research, suggested_hypothesis,
confidence}` — for the types: insider anomaly, supply disruption, price/fundamental divergence,
macro shock, sector rotation, sentiment extreme, liquidity imbalance.

Every opportunity is flagged `is_research_idea=True`, `is_trade_signal=False`, and
`requires_human_review=True`. Historical similarity comes from `recall`.

## Reuse & no-duplication
Reuses P73 hypothesis framing + P44 recall + P60 events; no new engine, no signal generation.

## Validation
`test_integration_p86_95.py`: research-idea-only (no trade signal), confidence from evidence,
multiple types.

## Files
`jarvis/research_workflow/opportunity_discovery.py`, `console_api.py`, this doc.
