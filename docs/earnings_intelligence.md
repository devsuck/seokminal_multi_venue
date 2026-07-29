# Earnings Intelligence (P100)

> Integration only — turns earnings into **research intelligence**. **Read-only, not a signal.**
> Deterministic.

## What it does — `jarvis/research_workflow/earnings_intelligence.py`
`analyze_earnings(earnings, *, assistant)` → **Earnings Event**
`{company, period, expected_metrics, actual_metrics, surprise, overall_surprise,
historical_comparison, related_strategy_impact, related_research}`.

Expectation vs reality per metric → `surprise_pct` and a label at ±5%:
`POSITIVE_SURPRISE | NEGATIVE_SURPRISE | IN_LINE`. `overall_surprise` is the majority label.
`related_strategy_impact` is deterministic research framing (not a trade):
- POSITIVE → `["post-earnings drift (PEAD)", "earnings momentum", "quality/growth"]`
- NEGATIVE → `["short-side PEAD", "value trap check", "estimate-revision"]`

A positive surprise triggers a recall of similar past earnings → a research update.
`stream(earnings_list)` batches into a review queue grouped by surprise.

## Reuse & no-duplication
Reuses research memory (`recall`), the event system, and opportunity-discovery framing. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `is_trade_signal=False`, `requires_human_review=True`.

## Validation
`test_integration_p96_100.py`: positive surprise + PEAD, negative/in-line labels, stream by-surprise,
AST safety.

## Files
`jarvis/research_workflow/earnings_intelligence.py`, `console_api.py` (`/console/earnings-intel`), this doc.
